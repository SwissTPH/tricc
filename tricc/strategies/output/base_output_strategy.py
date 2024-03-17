import abc
import logging
from tricc.models.tricc import stashed_node_func


logger = logging.getLogger("default")


class BaseOutPutStrategy:
    processes = ["main"]

    output_path = None
    # list of supported processes for the strategy,
    # the order of the list will be apply

    def __init__(self, output_path):
        self.output_path = output_path

    def execute(self, start_pages, pages):
        if "main" in start_pages:
            self.process_base(start_pages, pages=pages)
        else:
            logger.error("Main process required")

        logger.info("generate the relevance based on edges")

        # create relevance Expression
        self.process_relevance(start_pages, pages=pages)
        logger.info("generate the calculate based on edges")

        # create calculate Expression
        self.process_calculate(start_pages, pages=pages)
        logger.info("generate the export format")
        # create calculate Expression
        self.process_export(start_pages, pages=pages)

        logger.info("print the export")

        final_output = self.export(start_pages)
        return final_output

    ### walking function
    def process_base(self, start_pages, **kwargs):
        # for each node, check if condition is required issubclass(TriccNodeDisplayModel)
        # process name
        stashed_node_func(
            start_pages[self.processes[0]].root,
            self.generate_base,
            **{**self.get_kwargs(), **kwargs},
        )
        self.do_clean(**{**self.get_kwargs(), **kwargs})

    def process_relevance(self, start_pages, **kwargs):
        stashed_node_func(
            start_pages[self.processes[0]].root,
            self.generate_relevance,
            **{**self.get_kwargs(), **kwargs},
        )
        self.do_clean(**{**self.get_kwargs(), **kwargs})

    def process_calculate(self, start_pages, **kwargs):
        # call the strategy specific code
        stashed_node_func(
            start_pages[self.processes[0]].root,
            self.generate_calculate,
            **{**self.get_kwargs(), **kwargs},
        )
        self.do_clean(**{**self.get_kwargs(), **kwargs})

    def process_export(self, start_pages, **kwargs):
        stashed_node_func(
            start_pages[self.processes[0]].root,
            self.generate_export,
            **{**self.get_kwargs(), **kwargs},
        )
        self.do_clean(**{**self.get_kwargs(), **kwargs})

    # node function
    @abc.abstractmethod
    def generate_calculate(self, node, **kwargs):
        pass

    @abc.abstractmethod
    def generate_base(self, node, **kwargs):
        pass

    @abc.abstractmethod
    def generate_relevance(self, node, **kwargs):
        pass

    @abc.abstractmethod
    def generate_export(self, node, **kwargs):
        pass

    @abc.abstractmethod
    def export(self, **kwargs):
        return self

    ## Utils
    def do_clean(self, **kwargs):
        pass

    def get_kwargs(self):
        return {}
