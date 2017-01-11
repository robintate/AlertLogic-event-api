
import binascii
import time
import gzip
import subprocess
import os
import re
from string import printable
from alertlogic import *

def to_json():
    return


def to_string():
    return


class Event(AlertLogic):
    def __init__(self, event_id, customer_id):
        AlertLogic.__init__(self)
        self.event_id = event_id
        self.customer_id = customer_id
        self.event_url = ''  # set in get_event
        self.event_details = ''  # dict
        self.signature_details = ''  # dict
        self.event_payload = ''  # object --> EventPayload
        self.event_summary = ''  # object --> EventsPacketSummary
        self.get_event()  # triggers process to create this object

        def __get_signature_details(self, sig_id):
            primary_ur = 'https://scc.alertlogic.net/ids_signature/{0}'.format(sig_id)
            # backup in the event of a permissions issue to the primary url
            backup_url = 'https://console.clouddefender.alertlogic.com/signature.php?sid={0}'.format(sig_id)

            ################################################################################################################
            # temporary until the TODO below is resolved
            ############################################
            r = self.alogic.get(backup_url)
            winner = 'backup'
            if r.status_code != 200:
                return 'Failed to retrieve signature details :('

            # TODO: The primary url will not currently work with the way that Alert Logic implements their webpages because
            #   the SIDs do not directly align (SID in rule vs SID as they categorize it). Until this is resolved,
            #   the backup_url will be the only feasible option - thus meaning less data
            '''
            r = self.__alogic.get(primary_ur)
            winner = 'primary'
            if r.status_code != 200:
                r = self.__alogic.get(backup_url)
                winner = 'backup'
                if r.status_code != 200:
                    return 'Failed to retrieve signature details :('
            '''
            ################################################################################################################
            ################################################################################################################

            if winner == 'primary':
                sig_type = ''
                sig_rule = ''
                sig_references = ''
                sig_cve = ''
                sig_date = ''
                # logic for info
                # TODO: There is a problem with the regex for the sig_cve
                sig_details_search = re.search('<td>Classtype:\s*</td>[\s\n]+<td>(?P<sig_type>.*)</td>|'
                                               '<td>Detection:\s*</td>[\s\n]+<td>(?P<sig_rule>.*)</td>|'
                                               '<td>References:\s*</td>[\s\n]+<td>(?P<sig_references>.*)</td>|'
                                               '<td>Vulnerabilities:\s*</td>[\s\n]+<td>(?P<sig_cve>.*)[\s\n]*</td>|'
                                               '<td>Date\sAdded:\s*</td>[\s\n]+<td>(?P<sig_date>.*)</td>', r.text)
                if sig_details_search is not None:
                    # TODO: Will need to rework the exception handling logic here!
                    try:
                        sig_type = sig_details_search.group('sig_type')
                    except IndexError:
                        pass
                    try:
                        sig_rule = sig_details_search.group('sig_rule')
                    except IndexError:
                        pass
                    try:
                        sig_references = sig_details_search.group('sig_references')
                    except IndexError:
                        pass
                    try:
                        sig_cve = sig_details_search.group('sig_cve')
                    except IndexError:
                        pass
                    try:
                        sig_date = sig_details_search.group('sig_date')
                    except IndexError:
                        pass
                sig_details = {
                    'sig_id': sig_id,
                    'sig_type': sig_type,
                    'sig_rule': sig_rule,
                    'sig_references': sig_references,
                    'sig_cve': sig_cve,
                    'sig_date': sig_date
                }
                return sig_details

            elif winner == 'backup':
                sig_rule = ''
                # logic for info
                sig_details_search = re.search('<th>Signature\sContent</th>[\s\n]+<td>(?P<sig_rule>.*)</td>', r.text)
                if sig_details_search is not None:
                    sig_rule = sig_details_search.group('sig_rule')
                sig_details = {
                    'sig_id': sig_id,
                    'sig_rule': sig_rule
                    }
                return sig_details

    def __packet_analysis(self, payload): #request_payload, response_payload):
        """

        :param payload (str):
        :return:
        """
        restful_call = ''
        protocol = ''
        host = ''
        resource = ''
        response_code = 'None parsed'
        response_message = 'None parsed'
        # request
        rex_request = re.search(
            '(?P<restful_call>GET|POST|HEAD|TRACE|PUT)\s(?P<resource>[\S.]*)\s(?P<protocol>\S*)', payload)
        if rex_request:
            restful_call = rex_request.group('restful_call')             # GET
            resource = rex_request.group('resource')                     # /admin/blah
            protocol = rex_request.group('protocol')                     # HTTP/1.1
        rex_host = re.search('host:\s(?P<host>[\w\.-]*)', payload, re.I)  # www.example.com
        if rex_host:
            host = rex_host.group('host')
        # response
        rex_response = re.search('HTTP/[\d\.]+\s(?P<code>\d{3})\s(?P<message>[\w ]*)', payload)
        if rex_response:
            response_code = rex_response.group('code')                   # 302
            response_message = rex_response.group('message')             # Found
        packet_details = {
            'request_packet': {
                'restful_call':     restful_call,
                'protocol':         protocol,
                'host':             host,
                'resource':         resource,
                'full_url':         host + resource
                },
            'response_packet': {
                'response_code':    response_code,
                'response_message': response_message
                }
            }
        return packet_details

    def __gz_handler(self, event_id, converted_hex):
        """ Detects and decompresses gzipped hex """
        #TODO: make this public for use with the raw interactive methods????
        hold_hex = ''
        hold_bin = ''
        decompressed_data = '\n[*] Decompressed data detected'
        if '0d0a0d0a1f8b08' in converted_hex:  # 0d0a0d0a-packet header delineation, 1f8b08-gz signature
            hold_hex = converted_hex[converted_hex.find('0d0a0d0a1f8b08') + 8:]
        elif '1f8b08' in converted_hex:
            hold_hex = converted_hex[converted_hex.find('1f8b08'):]
        else:
            return ''
        if len(hold_hex) <= 20:  # per RFC1952, gzip header must contain at least 10 bytes (20 hex characters)
            decompressed_data += '\n[!] Unable to decompress. Too much missing data\n'
            return decompressed_data
        try:
            hold_bin = binascii.a2b_hex(hold_hex)
        except TypeError:
            decompressed_data += '\n[!] Potential zipped data detected but unable to convert - check event'
            return decompressed_data
        #############################################
        # TODO: Possibly implement
        #############################################
        #gz_handler = gzip.GzipFile(fileobj=hold_bin)
        #try:
            #decompressed_data += gz_handler.read()
            #return decompressed_data
        #############################################
        tmp_file_name = '/tmp/{0}_{1}.tmp'.format(event_id, time.time())  # unique name prevents overriding with threading
        with open(tmp_file_name, 'wb') as outfile:
            outfile.write(hold_bin)
        try:
            with gzip.open(tmp_file_name, 'rb') as f:
                decompressed_data += f.read()
        except Exception as e:
            decompressed_data += '\n[!] Missing zip data detected | Adding partial contents\n\n'
            output = subprocess.Popen(["zcat", tmp_file_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
            if output is None:
                # log error message with output[1]
                decompressed_data += '\n[!] Something went wrong with zcat output - check event'
            else:
                decompressed_data += output[0]
        if os.path.exists(tmp_file_name):
            os.remove(tmp_file_name)
        # would be really awesome to be able to decompress incomplete with zlib instead of fooling with zcat
        #return zlib.decompress(hold_bin, 16+zlib.MAX_WBITS)
        return decompressed_data

    def get_event(self):
        # self.event_id
        """
                Retrieves the event page, parses some descriptive fields for metadata, and cleans up then reconstructs
                the payload data. Returns
                """
        full_event = {}
        signature_details = {}
        source_address = ''
        dest_address = ''
        source_port = ''
        dest_port = ''
        signature_name = ''
        sensor = ''
        protocol = ''
        classification = ''
        severity = ''
        decompressed = ''
        packet_details = ''
        event_id = str(self.event_id)
        customer_id = str(self.customer_id)
        screen = 'event_monitor'
        filter_id = '0'
        event_url = 'https://console.clouddefender.alertlogic.com/event.php?id={0}&customer_id={1}&screen={2}&filter_id={3}'.format(
            event_id, customer_id, screen, filter_id)
        self.event_url = event_url  # set global url
        r = self.alogic.get(event_url, allow_redirects=False)
        # print r.status_code  # TODO: Add some exception handling here...try 3 times??? raise error? skip with message?
        if r.status_code != 200:
            raise NotAuthenticatedError('Failed to retrieve event #{0}. Status code: {1}. Reason: {2}'.format(
                event_id, r.status_code, r.reason))
        tmp_raw_page = str(r.text)
        ###################################################################
        # REGEX Event Details
        ###################################################################
        rex = re.compile(
            "var source_addr = '(?P<source_address>\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3})';\n" +
            "var dest_addr = '(?P<dest_address>\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3})';\n" +
            "var source_port = '(?P<source_port>\d{0,5})';\n" +
            "var dest_port = '(?P<dest_port>\d{0,5})';\n" +
            "var signature_name = '(?P<signature_name>[=/_()\.\w\s-]*)';\n" +
            "var sensor = '(?P<sensor>[\w\d-]*)';\n" +
            "var protocol = '(?P<protocol>\w*)';\n" +
            "var classification = '(?P<classification>[\w\s-]*)';\n" +
            "var severity = '(?P<severity>\d*)';\n")
        rex_results = rex.search(tmp_raw_page)
        if rex_results:
            source_address = rex_results.group('source_address')
            dest_address = rex_results.group('dest_address')
            source_port = rex_results.group('source_port')
            dest_port = rex_results.group('dest_port')
            signature_name = rex_results.group('signature_name')
            sensor = rex_results.group('sensor')
            protocol = rex_results.group('protocol')
            classification = rex_results.group('classification')
            severity = rex_results.group('severity')
        ########################################
        sig_id_search = re.search('<strong><a\shref="/signature.php\?[\w=&]*sid=(?P<sig_id>\d+).+', tmp_raw_page)
        if sig_id_search is not None:
            sig_id = sig_id_search.group('sig_id')
            # TODO: this should break into its own thread that joins right before the full event {} assembly
            signature_details = self.__get_signature_details(str(sig_id))
        ##################################################################
        ##################################################################
        #  The start and end parse are the most susceptible to breaking due to changes by Alert Logic!
        start_parse = str(r.text).find('<td>Signature: ') - 18
        end_parse = str(r.text).find('<table id="cache_table" style="display: none;">')
        parsed_html = str(r.text[start_parse:end_parse])
        raw_hex = ''
        for line in parsed_html.splitlines(True):
            hexstring = re.match(r'.*(0x[\da-f]{4}:[\s\da-f]+)\W', line.strip())
            if hexstring is not None:
                raw_hex += hexstring.string + '\n'
        # print raw_hex  # preserve this to print raw hex formatted
        raw2 = re.findall(r'(?<=0x[\da-fA_F]{4}:\s)\b[\da-fA-F]{4}\b|(?<=[\da-fA-F]{4}\s)\b[\da-fA-F]{4}\b', raw_hex)
        raw3 = ''  # this is the TRUE raw hex of the packets
        for chunk in raw2:
            raw3 += chunk
        full_payload1 = '{0}'.format(
            raw3.decode('hex').decode('ascii', 'ignore'))  # what is lost with ignore vs 'replace'
        full_payload = ''.join([c for c in full_payload1 if c in printable])
        packet_details = self.__packet_analysis(full_payload)
        decompressed = self.__gz_handler(event_id, raw3)
        full_event = {
            'event': event_id,
            'url': event_url,
            'details': {
                'source_addr': source_address,
                'dest_addr': dest_address,
                'source_port': source_port,
                'dest_port': dest_port,
                'signature_name': signature_name,
                'sensor': sensor,
                'protocol': protocol,
                'classification': classification,
                'severity': severity
            },
            'signature_details': signature_details,
            'payload': {
                'full_payload': full_payload,
                # 'request':             request_payload, #TODO: maybe
                # 'response':            response_payload,
                'packet_details': packet_details,
                'decompressed': decompressed
            }
        }
        return full_event
        return


################
################


    def set_event_details(self,
                      source_addr,
                      dest_addr,
                      source_port,
                      dest_port,
                      signature_name,
                      sensor,
                      protocol,
                      classification,
                      severity):

        event_details = {
            'source_addr': source_addr,
            'dest_addr': dest_addr,
            'source_port': source_port,
            'dest_port': dest_port,
            'signature_name': signature_name,
            'sensor': sensor,
            'protocol': protocol,
            'classification': classification,
            'severity': severity
            }
        self.event_details = event_details
        return

    def set_signature_details(self,
                            sig_id,
                            sig_type,
                            sig_rule,
                            sig_references,
                            sig_cve,
                            sig_date):

        sig_details = {
            'sig_id': sig_id,
            'sig_type': sig_type,
            'sig_rule': sig_rule,
            'sig_reference': list(sig_references),  # list?
            'sig_cve': sig_cve,
            'sig_date': sig_date
            }
        self.signature_details = sig_details

    def set_payload(self):
        return EventPayload()




###############################################################################
###############################################################################

#TODO!! CHANGED TO DICT
class EventDetails(object):
    # convert to list and move to Events??
    def __init__(self):
        self.source_addr = ''
        self.dest_addr = ''
        self.source_port = ''
        self.dest_port = ''
        self.signature_name = ''
        self.sensor = ''
        self.protocol = ''
        self.classification = ''
        self.severity = ''


###############################################################################
#TODO: CHANGED TO DICT
class EventSignatureDetais(object):
    # convert to list and move to Events??
    def __init__(self):
        self.sig_id = ''
        self.sig_type = ''
        self.sig_rule = ''
        self.sig_references = ''  # list?
        self.sig_cve = ''
        self.sig_date = ''


###############################################################################

class EventPayload(object):
    # belongs to Events
    def __init__(self):
        self.full_payload = ''
        self.decompressed = ''
        self.raw_hex = ''  # TODO: keep?  # could be useful for signature rule compares
        self.packet_details = ''  # object --> RequestPacketDetails


class PacketDetails(object):
    # belongs to EventPayload
    def __init__(self):
        self.request_packet = ''  # object --> RequestPacketDetails
        self.response_packet = ''  # object --> ResponsePacketDetails


###############################################################################

class RequestPacketDetails(object):
    # belongs to PacketDetails
    def __init__(self):
        self.restful_call = ''
        self.protocol = ''
        self.host = ''
        self.resource = ''
        self.full_url = ''


class ResponsePacketDetails(object):
    # belongs to PacketDetails
    def __init__(self):
        self.response_code = ''
        self.response_message = ''


