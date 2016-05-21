#
# lightify2mqtt - Bridge between OSRAM Lightify Gateway and MQTT
#
# Uses the documented "Lightify Cloud API" -- beware of the
# implications.
#
# Written and (C) 2016 by Oliver Wagner <owagner@tellerulam.com>
# Provided under the terms of the MIT license
#
# Requires:
# - Eclipse Paho for Python - http://www.eclipse.org/paho/clients/python/
# - requests 2.10.0 -- do manually upgrade using pip!
#

import argparse
import logging
import logging.handlers
import time
import socket
import paho.mqtt.client as mqtt
import serial
import io
import sys
import traceback
import requests
import json

version="0.1"
    
parser = argparse.ArgumentParser(description='Bridge between an OSRAM Lightify Gateway and MQTT')
parser.add_argument('--mqtt-host', default='localhost', help='MQTT server address. Defaults to "localhost"')
parser.add_argument('--mqtt-port', default='1883', type=int, help='MQTT server port. Defaults to 1883')
parser.add_argument('--mqtt-topic', default='lightify/', help='Topic prefix to be used for subscribing/publishing. Defaults to "lightify/"')
parser.add_argument('--clientid', default='modbus2mqtt', help='Client ID prefix for MQTT connection')
parser.add_argument('--user', required=True, help='Lightify Username')
parser.add_argument('--password', required=True, help='Lightify Password')
parser.add_argument('--serial', required=True, help='Lightify Gateway Serial (printed on device, WITHOUT suffix)')
parser.add_argument('--pollfreq', type=int, default=30, help='Polling interval in seconds. Defaults to 30')
parser.add_argument('--log', help='set log level to the specified value. Defaults to WARNING. Use DEBUG for maximum detail')
parser.add_argument('--syslog', action='store_true', help='enable logging to syslog')
args=parser.parse_args()

if args.log:
    logging.getLogger().setLevel(args.log)
if args.syslog:
    logging.getLogger().addHandler(logging.handlers.SysLogHandler())
else:
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))

topic=args.mqtt_topic
if not topic.endswith("/"):
    topic+="/"

devices={}
devicesByName={}
wakeup=False

logging.info('Starting lightify2mqtt V%s with topic prefix \"%s\"' %(version, topic))

def handleSetLights(name,msg):
	global devices,devicesByName
	# Find lamp
	dev=None
	parms={}
	if not name=="all":
		dev=devicesByName[name]
	try:
		val=float(msg.payload)
		if val==0:
			parms={"onoff":0}
		else:
			parms={"onoff":1,"level":val}
	except:
		# Seems to be complex type, try JSON
		parms=json.loads(msg.payload.decode("utf-8"))
	if dev==None:
		doRequest("device/all/set",parms)
	else:
		parms["idx"]=dev["deviceId"]
		doRequest("device/set",parms)

def handleSet(typeid,name,msg):
	if typeid=="lights":
		handleSetLights(name,msg)

def messagehandler(mqc,userdata,msg):
    global wakeup
    try:
        (cmd,typeid,name) = msg.topic[len(topic):].split("/")
        if cmd=="set":
        	handleSet(typeid,name,msg)
        	# Immediately wake up the polling loop
        	wakeup=True
        
    except Exception as e:
        logging.error("Error on message " + msg.topic + " :" + str(e))
        traceback.print_exc()
    
def connecthandler(mqc,userdata,rc):
    logging.info("Connected to MQTT broker with rc=%d" % (rc))
    mqc.subscribe(topic+"set/lights/#")
    mqc.subscribe(topic+"set/groups/#")
    mqc.publish(topic+"connected",1,qos=1,retain=True)

def disconnecthandler(mqc,userdata,rc):
    logging.warning("Disconnected from MQTT broker with rc=%d" % (rc))

def genEndpoint(ep):
	return "https://eu.lightify-api.org/lightify/services/"+ep;

def doRequest(ep,params=None):
	return requests.get(genEndpoint(ep),headers={
		"authorization": authtoken	
	},params=params)

def publishDevice(dev):
	if dev["on"]:
		val=dev["brightnessLevel"]
	else:
		val=0
	mqc.publish(topic+"status/lights/"+dev["name"],json.dumps({
		"val": val,
		"lightify_state": dev
	}),qos=1,retain=True)

def handleDevice(dev):
	global devices,devicesByName
	devid=dev["deviceId"]
	publish=True
	if devid in devices:
		olddev=devices[devid]
		# Any differences?
		if dev==olddev:
			publish=False
	devices[devid]=dev
	devicesByName[dev["name"]]=dev
	if publish:
		publishDevice(dev)

def pollDevices():
	r=doRequest("devices")
	if r.status_code==200:
		for dev in r.json():
			if dev["deviceType"]=="LIGHT":
				handleDevice(dev)
	return
	
def pollGroups():
	r=doRequest("groups")
	print(r.json())
	return

def doLightify():
	global authtoken,wakeup
	# First, login
	r=requests.get(genEndpoint("version"))
	logging.info("The remote gateway uses API version "+r.json()["apiversion"])
	r=requests.post(genEndpoint("session"),json={
		"username": args.user,
		"password": args.password,
		"serialNumber": args.serial
	})
	if(r.status_code>=400 and r.status_code<=499):
		logging.error("Authorization failed, check credentials! "+str(r.status_code)+" "+r.reason+" "+str(r.json()))
		sys.exit(1)
	authtoken=r.json()["securityToken"]
	logging.info("Successfully logged into remote gateway and obtained auth token for userID "+r.json()["userId"])
	mqc.publish(topic+"connected",2,qos=1,retain=True)
	while True:
		pollDevices()
		#pollGroups()
		for i in range(args.pollfreq):
			time.sleep(1)
			if wakeup:
				wakeup=False
				break

try:
    clientid=args.clientid + "-" + str(time.time())
    mqc=mqtt.Client(client_id=clientid)
    mqc.on_connect=connecthandler
    mqc.on_message=messagehandler
    mqc.on_disconnect=disconnecthandler
    mqc.will_set(topic+"connected",0,qos=2,retain=True)
    mqc.connect(args.mqtt_host,args.mqtt_port,60)
    mqc.loop_start()
    
    while True:
    	doLightify()
    	mqc.publish(topic+"connected",1,qos=1,retain=True)
      
except Exception as e:
    logging.error("Unhandled error [" + str(e) + "]")
    traceback.print_exc()
    sys.exit(1)
    