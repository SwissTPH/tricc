import abc

from tricc.models.tricc import stashed_node_func


class BaseInputStrategy:

    input_path = None
    def __init__(self, input_path):
        self.input_path = input_path
    

    ### walking function
    @abc.abstractmethod
    def build_tricc_graph(in_filepath, media_path):
        pass