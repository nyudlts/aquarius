from asnake.client import *
from electronbonder.client import *
import json
import logging
from os.path import join
import requests
from structlog import wrap_logger
from uuid import uuid4

from aquarius import settings

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger = wrap_logger(logger)


class ArchivesSpaceClientAuthError(Exception): pass


class ArchivesSpaceClientDataError(Exception): pass


class AuroraClientAuthError(Exception): pass


class AuroraClientDataError(Exception): pass


class AuroraClient(object):

    def __init__(self):
        self.log = logger.bind(transaction_id=str(uuid4()))
        self.client = ElectronBond(
            baseurl=settings.AURORA['baseurl'],
            username=settings.AURORA['username'],
            password=settings.AURORA['password'],
        )
        try:
            self.client.authorize()
        except ElectronBondAuthError:
            self.log.error("Couldn't authenticate user credentials for Aurora")
            raise AuroraClientAuthError("Couldn't authenticate user credentials for Aurora")

    def get(self, url):
        self.log = self.log.bind(request_id=str(uuid4()))
        resp = self.client.get(url)
        if resp.status_code != 200:
            self.log.error("Error retrieving data from Aurora: {msg}".format(msg=resp.json()['detail']))
            raise AuroraClientDataError("Error retrieving data from Aurora: {msg}".format(msg=resp.json()['detail']))
        self.log.debug("Object retrieved from Aurora", object=url)
        return resp.json()

    def update(self, url, data):
        self.log = self.log.bind(request_id=str(uuid4()))
        resp = self.client.put(url, data=json.dumps(data), headers={"Content-Type":"application/json"})
        if resp.status_code != 200:
            self.log.error("Error saving data in Aurora: {msg}".format(msg=resp.json()['detail']))
            raise AuroraClientDataError("Error saving data in Aurora: {msg}".format(msg=resp.json()['detail']))
        self.log.debug("Object saved in Aurora", object=url)
        return resp.json()


class ArchivesSpaceClient(object):

    def __init__(self):
        self.log = logger.bind(transaction_id=str(uuid4()))
        self.client = ASnakeClient(
            baseurl=settings.ARCHIVESSPACE['baseurl'],
            username=settings.ARCHIVESSPACE['username'],
            password=settings.ARCHIVESSPACE['password'],
        )
        if not self.client.authorize():
            self.log.error(
                "Couldn't authenticate user credentials for ArchivesSpace",
                object=settings.ARCHIVESSPACE['username'])
            raise ArchivesSpaceClientAuthError(
                "Couldn't authenticate user credentials for ArchivesSpace",
                object=settings.ARCHIVESSPACE['username'])
        self.repo_id = settings.ARCHIVESSPACE['repo_id']

    def create(self, data, type):
        self.log = self.log.bind(request_id=str(uuid4()))
        ENDPOINTS = {
            'component': 'repositories/{repo_id}/archival_objects'.format(repo_id=self.repo_id),
            'accession': 'repositories/{repo_id}/accessions'.format(repo_id=self.repo_id),
            'person': 'agents/people',
            'organization': 'agents/corporate_entities',
            'family': 'agents/families',
        }
        resp = self.client.post(ENDPOINTS[type], data=json.dumps(data))
        if resp.status_code != 200:
            self.log.error('Error creating object in ArchivesSpace: {msg}'.format(msg=resp.json()['error']))
            raise ArchivesSpaceClientDataError('Error creating object in ArchivesSpace: {msg}'.format(msg=resp.json()['error']))
        self.log.debug("Object created in Archivesspace", object=resp.json()['uri'])
        return resp.json()['uri']

    def get_or_create(self, type, field, value, last_updated, consumer_data):
        self.log = self.log.bind(request_id=str(uuid4()))
        TYPE_LIST = (
            ('family', 'agent_family', 'agents/families'),
            ('organization', 'agent_corporate_entity', 'agents/corporate_entities'),
            ('person', 'agent_person', 'agents/people'),
            ('component', 'archival_object', 'repositories/{repo_id}/archival_objects'.format(repo_id=self.repo_id)),
            ('grouping_component', 'archival_object', 'repositories/{repo_id}/archival_objects'.format(repo_id=self.repo_id)),
            ('accession', 'accession', 'repositories/{repo_id}/accessions'.format(repo_id=self.repo_id))
        )
        model_type = [t[1] for t in TYPE_LIST if t[0] == type][0]
        endpoint = [t[2] for t in TYPE_LIST if t[0] == type][0]
        query = json.dumps({"query": {"field": field, "value": value, "jsonmodel_type": "field_query"}})
        resp = self.client.get('search', params={"page": 1, "type[]": model_type, "aq": query})
        if resp.status_code != 200:
            self.log.error('Error searching for agent: {msg}'.format(msg=resp.json()['error']))
            raise ArchivesSpaceClientDataError('Error searching for agent: {msg}'.format(msg=resp.json()['error']))
        if len(resp.json()['results']) == 0:
            resp = self.client.get(endpoint, params={"all_ids": True, "modified_since": last_updated-120})
            if resp.status_code != 200:
                self.log.error('Error getting updated agents: {msg}'.format(msg=resp.json()['error']))
                raise ArchivesSpaceClientDataError('Error getting updated agents: {msg}'.format(msg=resp.json()['error']))
            for ref in resp.json():
                resp = self.client.get('{}/{}'.format(endpoint, ref))
                if resp.json()[field] == str(value):
                    return resp.json()['uri']
            self.log.debug("No match for object found in ArchivesSpace", object=value)
            return self.create(consumer_data, type)
        return resp.json()['results'][0]['uri']
