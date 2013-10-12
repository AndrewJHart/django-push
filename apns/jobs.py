import socket, ssl, pprint, struct, time, binascii, random, json, os, logging
from apns.models import APNSToken,APNSAlert,APNSAPSPayload,APNSMessage,APNSData1,MsgQueue
from django.conf import settings
from django.db import transaction
from apns.APNSSocket import APNSSocket
from constants import *

logger = logging.getLogger(__name__)

def getItemFor(itemNumber,data):
	return struct.pack("!BH%ds"%(len(data)),itemNumber,len(data),data)

def getItemWithLengthFor(itemNumber,data,dataLength):
	if dataLength == 4:
		return struct.pack("!BHI",itemNumber,dataLength,data)
	else:
		return struct.pack("!BHB",itemNumber,dataLength,data)

def getPacket(deviceToken,payload,identifier):
	command=2
	expiry = time.time()
	deviceTokenHex = binascii.unhexlify(deviceToken)
	priority = 10

	tokenItem = getItemFor(1,deviceTokenHex)
	payloadItem = getItemFor(2,payload)

	identifierItem = getItemWithLengthFor(3,identifier,4)
	expiryItem = getItemWithLengthFor(4,int(expiry),4)
	priorityItem = getItemWithLengthFor(5,priority,1)

	frame = tokenItem + payloadItem + identifierItem + expiryItem + priorityItem

	packetFormat = "!BI"
	packet = struct.pack(packetFormat,command,len(frame)) + frame 
	return packet

def pushapns():
	apnssock = APNSSocket() 
	apnssock.connect()

	logger.info('Connected to APNS')

	with transaction.commit_on_success():

		msgqueue = MsgQueue.objects.all().filter(msg_sent=False).order_by('id')

		for entry in msgqueue:
			logger.info('Pushing Msg:' + str(entry.id))
			payload = json.dumps(entry.apnsmessage.aps_payload.to_dict())

			# Limit the payload to 256
			if len(payload) > PAYLOAD_LIMIT:
				entry.error = PAYLOAD_LIMIT_EXCEEDED
				entry.msg_sent=True
				entry.save()
				continue

			deviceToken = entry.apnstoken.token
			try:
				totalBytes = apnssock.apnssend(getPacket(deviceToken,payload,entry.id))
			except RuntimeError:
				""" 
				APNS closes connection after receiving the errored packet.
				Since we push messages in the msgqueue oredered by id, id-1 gives the errored message.
				"""
				erroredmsg = MsgQueue.objects.all().get(pk=entry.id-1)
				erroredmsg.error = MALFORMED_PACKET

				# Re-establish ssl connection
				apnssock = APNSSocket() 
				apnssock.connect()

			entry.msg_sent=True
			entry.save()
			# print "totalBytes = %d" %(totalBytes)

	logger.info('Close APNS Connection')
	apnssock.close()