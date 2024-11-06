import abc

import logging

logger = logging.getLogger("default")


class BaseTransformStrategy:
    @classmethod
    def __init__(cls, project, **kwargs):
        cls.project = project

    ### walking function
    @abc.abstractmethod
    def execute(**kwargs):
        pass
