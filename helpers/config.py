#import configparser

import argparse
import yaml


class Config:
    __instance = None
    __role = None
    __document = None

    @staticmethod
    def get_instance():
        """ Static access method. """
        if Config.__instance == None:
            Config()
        return Config.__instance 

    def __init__(self):
        """ Virtually private constructor. """
        if Config.__instance != None:
            raise Exception("This class is a singleton!")
        else:
            Config.__instance = self

    def load(self, yaml_file, role):
        self.__role = role
        self.__document = yaml.load(yaml_file)

    def get_all(self):
        return self.__document

    def get_role(self):
        return self.__role

    def get_our_section(self):
        return self.__document[self.__role]


config = Config()


def parse_config_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--config', default='config.yaml', metavar='config.yaml')
    parser.add_argument(
        '--role', required=True, metavar='<role>',
        help='')
    prog_args = parser.parse_args()
    config.load(prog_args.config, prog_args.role)

# e.g. ['10.0.0.1:5001']
def get_our_worker_list():
    section = config.get_our_section()
    if section['role_type'] != 'mn':
        raise RuntimeError('expected \'role_type: \'mn\'\'')
    worker_hosts = []
    for worker_desc in section['workers']:
        worker_hosts.append(worker_desc['address'])
    return worker_hosts

def get_full_worker_list():
    worker_hosts = []
    for role_desc in config.get_all():
        if role_desc['role_type'] != 'mn':
            continue
        for worker_desc in role_desc['workers']:
            worker_hosts.append(worker_desc['address'])
    return worker_hosts

# e.g. ['172.17.0.2:5000']
def get_ps_host_list():
    ps_hosts = []
    for role_desc in config.get_all():
        if role_desc['role_type'] != 'ps':
            continue
        ps_hosts.append(role_desc['address'])
    return ps_hosts

"""
ps1:
  role_type: 'ps'
  address: '172.17.0.2:5000'
  task_index: 0

mn1:
  role_type: 'mn'
  nat_ip: '10.0.0.254'
  task_index: 0
  workers:
    - id: 0
      address: '10.0.0.1:5001'
    - id: 1
      address: '10.0.0.2:5001'
"""
