#
# Copyright (C) 2013 Webvirtmgr.
#
import string
from vrtManager import util
from vrtManager.connection import wvmConnect

from webvirtmgr.settings import QEMU_CONSOLE_DEFAULT_TYPE


def get_rbd_storage_data(stg):
    xml = stg.XMLDesc(0)
    ceph_user = util.get_xml_path(xml, "/pool/source/auth/@username")

    def get_ceph_hosts(ctx):
        hosts = []
        for host in ctx.xpathEval("/pool/source/host"):
            name = host.prop("name")
            if name:
                hosts.append({'name': name, 'port': host.prop("port")})
        return hosts
    ceph_hosts = util.get_xml_path(xml, func=get_ceph_hosts)
    secret_uuid = util.get_xml_path(xml, "/pool/source/auth/secret/@uuid")
    return ceph_user, secret_uuid, ceph_hosts


class wvmCreate(wvmConnect):
    def get_storages_images(self):
        """
        Function return all images on all storages
        """
        images = []
        storages = self.get_storages()
        for storage in storages:
            stg = self.get_storage(storage)
            try:
                stg.refresh(0)
            except:
                pass
            for img in stg.listVolumes():
                if img.endswith('.iso'):
                    pass
                else:
                    images.append(img)
        return images

    def get_os_type(self):
        """Get guest capabilities"""
        return util.get_xml_path(self.get_cap_xml(), "/capabilities/guest/os_type")

    def get_host_arch(self):
        """Get guest capabilities"""
        return util.get_xml_path(self.get_cap_xml(), "/capabilities/host/cpu/arch")

    def get_cache_modes(self):
        """Get cache available modes"""
        return {
            'default': 'Default',
            'none': 'Disabled',
            'writethrough': 'Write through',
            'writeback': 'Write back',
            'directsync': 'Direct sync',  # since libvirt 0.9.5
            'unsafe': 'Unsafe',  # since libvirt 0.9.7
        }

    def create_volume(self, storage, name, size, format='qcow2', metadata=False):
        size = int(size) * 1073741824
        stg = self.get_storage(storage)
        storage_type = util.get_xml_path(stg.XMLDesc(0), "/pool/@type")
        if storage_type == 'dir':
            name += '.img'
            alloc = 0
        else:
            alloc = size
            metadata = False
        xml = """
            <volume>
                <name>%s</name>
                <capacity>%s</capacity>
                <allocation>%s</allocation>
                <target>
                    <format type='%s'/>
                </target>
            </volume>""" % (name, size, alloc, format)
        stg.createXML(xml, metadata)
        try:
            stg.refresh(0)
        except:
            pass
        vol = stg.storageVolLookupByName(name)
        return vol.path()

    def get_volume_type(self, path):
        vol = self.get_volume_by_path(path)
        vol_type = util.get_xml_path(vol.XMLDesc(0), "/volume/target/format/@type")
        if vol_type == 'unknown':
            return 'raw'
        if vol_type:
            return vol_type
        else:
            return 'raw'

    def get_volume_path(self, volume):
        storages = self.get_storages()
        for storage in storages:
            stg = self.get_storage(storage)
            if stg.info()[0] != 0:
                stg.refresh(0)
                for img in stg.listVolumes():
                    if img == volume:
                        vol = stg.storageVolLookupByName(img)
                        return vol.path()

    def get_storage_by_vol_path(self, vol_path):
        vol = self.get_volume_by_path(vol_path)
        return vol.storagePoolLookupByVolume()

    def clone_from_template(self, clone, template, metadata=False):
        vol = self.get_volume_by_path(template)
        stg = vol.storagePoolLookupByVolume()
        storage_type = util.get_xml_path(stg.XMLDesc(0), "/pool/@type")
        format = util.get_xml_path(vol.XMLDesc(0), "/volume/target/format/@type")
        if storage_type == 'dir':
            clone += '.img'
        else:
            metadata = False
        xml = """
            <volume>
                <name>%s</name>
                <capacity>0</capacity>
                <allocation>0</allocation>
                <target>
                    <format type='%s'/>
                </target>
            </volume>""" % (clone, format)
        stg.createXMLFrom(xml, vol, metadata)
        clone_vol = stg.storageVolLookupByName(clone)
        return clone_vol.path()

    def _defineXML(self, xml):
        self.wvm.defineXML(xml)

    def delete_volume(self, path):
        vol = self.get_volume_by_path(path)
        vol.delete()

    def create_instance(self, name, memory, vcpu, host_model, uuid, images, cache_mode, networks, virtio, mac=None):
        """
        Create VM function
        """
        memory = int(memory) * 1024

        if self.is_kvm_supported():
            hypervisor_type = 'kvm'
        else:
            hypervisor_type = 'qemu'

        xml = """
                <domain type='%s' xmlns:qemu='http://libvirt.org/schemas/domain/qemu/1.0'>
                  <name>%s</name>
                  <description>None</description>
                  <uuid>%s</uuid>
                  <memory unit='KiB'>%s</memory>
                  <vcpu>%s</vcpu>""" % (hypervisor_type, name, uuid, memory, vcpu)
        if host_model:
            xml += """<cpu mode='host-model'/>"""
        xml += """<os>
                    <type arch='%s'>%s</type>
                    <boot dev='hd'/>
                    <boot dev='cdrom'/>
                    <bootmenu enable='yes'/>
                  </os>""" % (self.get_host_arch(), self.get_os_type())
        xml += """<features>
                    <acpi/><apic/><pae/>
                  </features>
                  <clock offset="localtime">
                    
                  </clock>
                  <on_poweroff>destroy</on_poweroff>
                  <on_reboot>restart</on_reboot>
                  <on_crash>restart</on_crash>
                  <devices>"""

        disk_letters = list(string.lowercase)
        for image, img_type in images.items():
            stg = self.get_storage_by_vol_path(image)
            stg_type = util.get_xml_path(stg.XMLDesc(0), "/pool/@type")

            if stg_type == 'rbd':
                ceph_user, secret_uuid, ceph_hosts = get_rbd_storage_data(stg)
                xml += """<disk type='network' device='disk'>
                            <driver name='qemu' type='%s' cache='%s'/>
                            <auth username='%s'>
                                <secret type='ceph' uuid='%s'/>
                            </auth>
                            <source protocol='rbd' name='%s'>""" % (img_type, cache_mode, ceph_user, secret_uuid, image)
                if isinstance(ceph_hosts, list):
                    for host in ceph_hosts:
                        if host.get('port'):
                            xml += """
                                   <host name='%s' port='%s'/>""" % (host.get('name'), host.get('port'))
                        else:
                            xml += """
                                   <host name='%s'/>""" % host.get('name')
                xml += """
                            </source>"""
            else:
                xml += """<disk type='file' device='disk'>
                            <driver name='qemu' type='%s' cache='%s'/>
                            <source file='%s'/>""" % (img_type, cache_mode, image)

            if virtio:
                xml += """<target dev='vd%s' bus='virtio'/>""" % (disk_letters.pop(0),)
            else:
                xml += """<target dev='sd%s' bus='ide'/>""" % (disk_letters.pop(0),)
            xml += """</disk>"""

        xml += """  <disk type='file' device='cdrom'>
                      <driver name='qemu' type='raw'/>
                      <source file=''/>
                      <target dev='hda' bus='ide'/>
                      <readonly/>
                      <address type='drive' controller='0' bus='1' target='0' unit='1'/>
                    </disk>"""
        for net in networks.split(','):
            xml += """<interface type='network'>"""
            if mac:
                xml += """<mac address='%s'/>""" % mac
            xml += """<source network='%s'/>""" % net
            if virtio:
                xml += """<model type='virtio'/>"""
            xml += """</interface>"""

        xml += """  <input type='mouse' bus='ps2'/>
                    <input type='tablet' bus='usb'/>
                    <sound model='ich6'>
                        <alias name='sound0'/>
                        <address type='pci' domain='0x0000' bus='0x00' slot='0x06' function='0x0'/>
                    </sound>
                    <graphics type='%s' port='-1' autoport='yes' listen='0.0.0.0'>
                      <listen type='address' address='0.0.0.0'/>
                    </graphics>
                    <console type='pty'/>
                    <video>
                      <model type='cirrus'/>
                    </video>
                    <memballoon model='virtio'/>
                  </devices>
                </domain>""" % QEMU_CONSOLE_DEFAULT_TYPE
        self._defineXML(xml)
