import abc

import logging

logger = logging.getLogger("default")


class BaseInputStrategy:
    input_path = None    
    def __init__(self, input_path):
        self.input_path = input_path

    ### walking function
    @abc.abstractmethod
    def execute(in_filepath, media_path):
        pass
