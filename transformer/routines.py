import json
import logging
from structlog import wrap_logger
from uuid import uuid4

from aquarius import settings

from .clients import ArchivesSpaceClient, UrsaMajorClient
from .models import Package
from .transformers import DataTransformer

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger = wrap_logger(logger)


class RoutineError(Exception): pass


class Routine:
    def __init__(self):
        self.aspace_client = ArchivesSpaceClient()
        self.ursa_major_client = UrsaMajorClient()
        self.transformer = DataTransformer(aspace_client=self.aspace_client)
        self.log = logger


class AccessionRoutine(Routine):

    def run(self):
        self.log.bind(request_id=str(uuid4()))
        packages = Package.objects.filter(process_status=10)
        accession_count = 0

        for package in packages:
            self.log.debug("Running AccessionTransferRoutine", object=package)
            try:
                package.transfer_data = self.ursa_major_client.find_bag_by_id(package.identifier)
                package.accession_data = self.ursa_major_client.retrieve(package.transfer_data['accession'])
                if not package.accession_data.get('archivesspace_identifier'):
                    self.save_new_accession(package)
                    accession_count += 1
                package.process_status = 20
                package.save()
            except Exception as e:
                raise RoutineError("Accession error: {}".format(e))
        return "{} accessions saved.".format(accession_count)

    def save_new_accession(self, package):
        transformed_data = self.transformer.transform_accession(package.accession_data['data'])
        accession_identifier = self.aspace_client.create(transformed_data, 'accession')
        package.accession_data['archivesspace_identifier'] = accession_identifier
        for p in package.accession_data['data']['transfers']:
            for sibling in Package.objects.filter(identifier=p['identifier']):
                sibling.accession_data = package.accession_data
                sibling.save()


class GroupingComponentRoutine(Routine):

    def run(self):
        self.log.bind(request_id=str(uuid4()))
        packages = Package.objects.filter(process_status=20)
        grouping_count = 0

        for p in packages:
            try:
                package = Package.objects.get(id=p.pk)
                if not package.transfer_data.get('archivesspace_parent_identifier'):
                    self.save_new_grouping_component(package)
                    grouping_count += 1
                package.process_status = 30
                package.save()
            except Exception as e:
                raise RoutineError("Grouping component error: {}".format(e))
        return "{} grouping components saved.".format(grouping_count)

    def save_new_grouping_component(self, package):
        transformed_data = self.transformer.transform_grouping_component(package.accession_data['data'])
        parent = self.aspace_client.create(transformed_data, 'component')
        package.transfer_data['archivesspace_parent_identifier'] = parent
        for p in package.accession_data['data']['transfers']:
            for sibling in Package.objects.filter(identifier=p['identifier']):
                sibling.transfer_data['archivesspace_parent_identifier'] = parent
                sibling.save()


class TransferComponentRoutine(Routine):

    def run(self):
        self.log.bind(request_id=str(uuid4()))
        packages = Package.objects.filter(process_status=30)
        transfer_count = 0

        for p in packages:
            try:
                package = Package.objects.get(id=p.pk)
                if not package.transfer_data.get('archivesspace_identifier'):
                    self.transformer.resource = package.accession_data['data']['resource']
                    self.transformer.parent = package.transfer_data['archivesspace_parent_identifier']
                    self.save_new_transfer_component(package)
                    transfer_count += 1
                package.process_status = 40
                package.save()
            except Exception as e:
                raise RoutineError("Transfer component error: {}".format(e))
        return "{} transfer components created.".format(transfer_count)

    def save_new_transfer_component(self, package):
        transformed_data = self.transformer.transform_component(package.transfer_data['data'])
        transfer_identifier = self.aspace_client.create(transformed_data, 'component')
        package.transfer_data['archivesspace_identifier'] = transfer_identifier
        for sibling in Package.objects.filter(identifier=package.identifier):
            sibling.transfer_data['archivesspace_identifier'] = transfer_identifier
            sibling.save()


class DigitalObjectRoutine(Routine):

    def run(self):
        self.log.bind(request_id=str(uuid4()))
        packages = Package.objects.filter(process_status=40)
        digital_count = 0

        for p in packages:
            try:
                package = Package.objects.get(id=p.pk)
                self.save_new_digital_object(package)
                digital_count += 1
                package.process_status = 50
                package.save()
            except Exception as e:
                raise RoutineError("Digital object error: {}".format(e))
        return "{} digital objects saved.".format(digital_count)

    def save_new_digital_object(self, package):
        transformed_data = self.transformer.transform_digital_object(package)
        do_identifier = self.aspace_client.create(transformed_data, 'digital object')
        transfer_component = self.aspace_client.retrieve(package.transfer_data['archivesspace_identifier'])
        transfer_component['instances'].append(
            {"instance_type": "digital_object",
             "jsonmodel_type": "instance",
             "digital_object": {"ref": do_identifier}
             })
        updated_component = self.aspace_client.update(package.transfer_data['archivesspace_identifier'], transfer_component)
