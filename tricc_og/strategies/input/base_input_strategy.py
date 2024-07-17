import abc

from tricc_oo.models import (
    TriccNodeMainStart,
    TriccNodeActivity,
    TriccEdge,
)
from tricc_oo.converters.utils import generate_id
from tricc_oo.visitors.tricc import get_activity_wait, stashed_node_func, set_prev_next_node
from itertools import chain
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
