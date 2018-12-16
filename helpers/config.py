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
        stream = open(yaml_file, 'r')
        self.__document = yaml.load(stream)

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
        '-c', '--config', default='config.yaml', metavar='config.yaml')
    parser.add_argument(
        'role', metavar='<role>', help='role section reference')
    prog_args = parser.parse_args()
    config.load(prog_args.config, prog_args.role)

# e.g. [{'task_index': 0, 'address': '10.0.0.1:5001'}]
def get_our_worker_list():
    section = config.get_our_section()
    if section['role_type'] != 'mn':
        raise RuntimeError('expected \'role_type: \'mn\'\'')
    workers = []
    for worker_desc in section['workers']:
        workers.append(worker_desc)
    return workers

def get_full_worker_list():
    workers = []
    document = config.get_all()
    for role_name in document:
        role_desc = document[role_name]
#        print('dump:', yaml.dump(role_desc))
        if role_desc['role_type'] != 'mn':
            continue
        for worker_desc in role_desc['workers']:
            workers.append(worker_desc)
    return workers

# e.g. [{'task_index': 0, 'address': '172.17.0.2:5000'}]
def get_ps_list():
    ps_list = []
    document = config.get_all()
    for role_name in document:
        role_desc = document[role_name]
#        print(yaml.dump(role_desc))
#        print(role_desc['role_type'])
        if role_desc['role_type'] != 'ps':
            continue
        ps_list.append(role_desc)
    return ps_list
