#
# lightify2mqtt - Bridge between OSRAM Lightify Gateway and MQTT
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
import signal
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
parser.add_argument('--serial', required=True, help='Lightify Gateway serial')
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

logging.info('Starting lightify2mqtt V%s with topic prefix \"%s\"' %(version, topic))

def signal_handler(signal, frame):
        print('Exiting ' + sys.argv[0])
        sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)

def messagehandler(mqc,userdata,msg):
    try:
        (prefix,function,slaveid,functioncode,register) = msg.topic.split("/")
        
    except Exception as e:
        logging.error("Error on message " + msg.topic + " :" + str(e))
    
def connecthandler(mqc,userdata,rc):
    logging.info("Connected to MQTT broker with rc=%d" % (rc))
    mqc.subscribe(topic+"set/#")
    mqc.publish(topic+"connected",1,qos=1,retain=True)
    mqc.will_set(topic+"connected",0,qos=2,retain=True)

def disconnecthandler(mqc,userdata,rc):
    logging.warning("Disconnected from MQTT broker with rc=%d" % (rc))

def genEndpoint(ep):
	return "https://eu.lightify-api.org/lightify/services/"+ep;

def doLightify():
	# First, login
	r=requests.get(genEndpoint("version"))
	logging.info("Gateway uses API version "+r.json()["apiversion"])
	r=requests.post(genEndpoint("session"),json={
		"username": args.user,
		"password": args.password,
		"serialNumber": args.serial
	})
	if(r.status_code>=400 and r.status_code<=499):
		logging.error("Authorization failed, check credentials! "+str(r.status_code)+" "+r.reason)
		sys.exit(1)
	mqc.publish(topic+"connected",2,qos=1,retain=True)
	while True:
		time.sleep(10)

try:
    clientid=args.clientid + "-" + str(time.time())
    mqc=mqtt.Client(client_id=clientid)
    mqc.on_connect=connecthandler
    mqc.on_message=messagehandler
    mqc.on_disconnect=disconnecthandler
    mqc.disconnected=True
    mqc.connect(args.mqtt_host,args.mqtt_port,60)
    mqc.loop_start()
    
    while True:
    	doLightify()
    	mqc.publish(topic+"connected",1,qos=1,retain=True)
      
except Exception as e:
    logging.error("Unhandled error [" + str(e) + "]")
    sys.exit(1)
    