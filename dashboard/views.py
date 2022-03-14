from contextlib import nullcontext
from distutils.command.config import config
from fileinput import close
import imp
from importlib import resources
from inspect import isclass
import json
from multiprocessing import context
from nis import cat
from operator import truediv
from re import L, S, template
import re
from tempfile import tempdir
from traceback import print_tb
from urllib.request import Request
from wsgiref.util import request_uri
from django.shortcuts import render
import requests
from datetime import datetime, timedelta

# Create your views here.

from django.http import HttpResponse
from django.template import loader

def GenerateOccupancyParam(dateQuery):
    """
    Create the param in getting from Gov API

    Params:
    Querying date, dd/mm/yyyy

    Returns:
    String of the value of key q
    """
    occupancyQuery = {}
    occupancyQuery['resource'] = "http://www.chp.gov.hk/files/misc/occupancy_of_quarantine_centres_eng.csv"
    occupancyQuery['section'] = 1
    occupancyQuery['format'] = 'json'
    occupancyQuery['sorts'] = [ [ 8, 'desc' ] ]
    filterDate = []
    filterDate.append(dateQuery)
    filterList = [ [ 1, 'eq', filterDate ] ]
    occupancyQuery['filters'] = filterList
    return json.dumps(occupancyQuery)

def GenerateConfinesParam(dateQuery):
    """
    Create the param in getting data from Gov confines API

    Params:
    Querying date, dd/mm/yyyy

    Returns:
    String of the value of key q
    """
    confinesParams = {}
    confinesParams['resource'] = 'http://www.chp.gov.hk/files/misc/no_of_confines_by_types_in_quarantine_centres_eng.csv'
    confinesParams['section'] = 1
    confinesParams['format'] = 'json'
    confinesParams['filters'] = [ [ 1, 'eq', [ dateQuery ] ] ]
    return json.dumps(confinesParams)

def RequestDatasetByDate(dateQuery):
    '''
    Returns:
    {
        isConnected: bool, True for connected
        isEmpty: bool, False for not empty
        occupancy: Object
        confines: Object
    }
    '''
    returnObj = {}
    isConnected = False
    isEmpty = True

    occupancyParams = GenerateOccupancyParam(dateQuery)
    confinesParams = GenerateConfinesParam(dateQuery)
    
    try:
        occupancyResponse = requests.get('https://api.data.gov.hk/v2/filter', params = {"q" : occupancyParams})
        confinesResponse = requests.get('https://api.data.gov.hk/v2/filter', params = {"q" : confinesParams})

    except requests.exceptions.ConnectionError:
        print('Connection Error')
    else:
        if (occupancyResponse.status_code == 200 and confinesResponse.status_code == 200):
            isConnected = True
            occupancyObj = json.loads(occupancyResponse.text)
            confinesObj = json.loads(confinesResponse.text)
            #Data set today is not avaliable
            if (len(occupancyObj) == 0 or len(confinesObj) == 0):
                isEmpty = True
            else:
                #No exception
                isEmpty = False
                returnObj['occupancy'] = occupancyObj
                returnObj['confines'] = confinesObj
        else:
            isConnected = False
    finally:
        returnObj['isConnected'] = isConnected
        returnObj['isEmpty'] = isEmpty
        return returnObj


def index(request):

    context = {}
    data = {}
    centres = []

    dt = datetime.now()
    dateQuery = dt.strftime('%d/%m/%Y')
    r = RequestDatasetByDate(dateQuery)

    for _ in range (7):
        print ('Requesting date', dateQuery)
        if (r['isConnected'] == True):
            context['connected'] = True

            if (r['isEmpty'] == False):
                #Normal case
                data['date'] = dateQuery
                context['has_data'] = True
                occupancyObj = r['occupancy']
                confinesObj = r['confines']               
                
                unitInUse = 0
                unitAvaliable = 0
                personQuarantined = 0
                for i in range(len(occupancyObj)):
                    unitInUse += occupancyObj[i]['Current unit in use']
                    unitAvaliable += occupancyObj[i]['Ready to be used (unit)']
                    personQuarantined += occupancyObj[i]['Current person in use']
                data['units_in_use'] = unitInUse
                data['units_available'] = unitAvaliable
                data['persons_quarantined'] = personQuarantined

                for i in range(3):
                    centre = {
                        "name" : occupancyObj[i]['Quarantine centres'],
                        'units' : occupancyObj[i]['Ready to be used (unit)']
                    }
                    centres.append(centre)
                context['centres'] = centres

                closeContacts = confinesObj[0]['Current number of close contacts of confirmed cases']
                nonCloseContacts = confinesObj[0]['Current number of non-close contacts']
                data['non_close_contacts'] = nonCloseContacts
                data['count_consistent'] = (personQuarantined == closeContacts + nonCloseContacts)
                context['data'] = data
                break
            else:
                #Empty, request previous data
                dt = dt + timedelta(days=-1)
                dateQuery = dt.strftime('%d/%m/%Y')
                r = RequestDatasetByDate(dateQuery)
                continue
        else:
            context['connected'] = False
            break
    else:
        #No data in 7 days
        context['has_data'] = False

    return render(request, 'index.html', context)
