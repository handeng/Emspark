# Create your views here.
from django.contrib.auth import authenticate, login
from django.http import HttpResponseRedirect, HttpResponse
import json
import base64


def auth(request):
    status = 0
    msg = "null"
    if 'HTTP_AUTHORIZATION' in request.META:
        auth = request.META['HTTP_AUTHORIZATION'].split()
        if len(auth) == 2:
            if auth[0].lower() == "basic":
                uname, passwd = base64.b64decode(auth[1]).split(':')
                user = authenticate(username=uname, password=passwd)
                if user is not None and user.is_active:
                    login(request, user)
                    status = 1
                    msg = "login ok"
                else:
                    status = 0
                    msg = "login error"


    data = json.dumps({'status': msg})
    response = HttpResponse()
    response['Content-Type'] = "text/javascript"
    response.write(data)
    return response


def auth_post(request):
    usr = request.POST['username']
    pwd = request.POST['password']
    user = authenticate(username=usr,password=pwd)
    if user is not None:
        if user.is_active:
            login(request, user)
            msg = "login"
        else:
            msg = "deactive"
    else:
        msg = "not exist"
    data = json.dumps({'status': msg})
    response = HttpResponse()
    response['Content-Type'] = "text/javascript"
    response.write(data)
    return response


def auth_get(request,usr,pwd):
    user = authenticate(username=usr,password=pwd)
    if user is not None:
        if user.is_active:
            login(request, user)
            msg = "login"
        else:
            msg = "deactive"
    else:
        msg = "not exist"
    data = json.dumps({'status': msg})
    response = HttpResponse()
    response['Content-Type'] = "text/javascript"
    response.write(data)
    return response
