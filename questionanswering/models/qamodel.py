import abc
import keras
import numpy as np
import os
import tqdm
from collections import deque
from construction import graph
from datasets import evaluation
from utils import Loggable
from wikidata import wdaccess


class QAModel(Loggable, metaclass=abc.ABCMeta):
    """
    A QAModel measures a similarity between a sentence and a set of candidate semantic graphs.
    """

    def __init__(self, parameters, **kwargs):
        self._p = parameters
        super(QAModel, self).__init__(parameters=parameters, **kwargs)

    @abc.abstractmethod
    def encode_data_instance(self, instance):
        """
        Encode a single data instance in a format acceptable by the model.
        A data instance is a list of possible graphs.

        :param instance: a list of possible graphs for a single question.
        :return: a tuple that represents the instance in the model format.
        """

    def test(self, data_with_gold, verbose=False):
        graphs, gold_answers = data_with_gold
        predicted_indices = self.apply_on_batch(graphs, verbose=verbose)
        successes = deque()
        avg_metrics = np.zeros(3)
        for i, sorted_indices in enumerate(tqdm.tqdm(predicted_indices, ascii=True, disable=(not verbose))):
            sorted_indices = deque(sorted_indices)
            if sorted_indices:
                retrieved_answers = []
                while not retrieved_answers and sorted_indices:
                    index = sorted_indices.popleft()
                    g = graphs[i][index]
                    retrieved_answers = wdaccess.query_graph_denotations(g)
                retrieved_answers = wdaccess.label_query_results(retrieved_answers)
                metrics = evaluation.retrieval_prec_rec_f1_with_altlabels(gold_answers[i], retrieved_answers)
                if metrics[-1]:
                    successes.append((i, metrics[-1], g))
                avg_metrics += metrics
        avg_metrics /= len(gold_answers)
        return successes, avg_metrics

    def test_on_silver(self, data_with_targets, verbose=False):
        graphs, targets = data_with_targets
        if len(targets) > 0 and not issubclass(type(targets[0]), np.integer):
            targets = np.argmax(targets, axis=-1)
        predicted_targets = [int(indices[0]) if len(indices) > 0 else 0 for indices in self.apply_on_batch(graphs, verbose)]
        accuracy = np.sum(np.asarray(predicted_targets) == targets) / len(targets)
        return accuracy, predicted_targets

    def apply_on_batch(self, data_batch, verbose=False):
        predicted_indices = deque()
        for instance in tqdm.tqdm(data_batch, ascii=True, ncols=100, disable=(not verbose)):
            predicted_indices.append(self.apply_on_instance(instance) if instance else [])
        return predicted_indices

    def apply_on_instance(self, instance):
        predictions = self.scores_for_instance(instance)
        return np.argsort(predictions)[::-1]

    @abc.abstractmethod
    def scores_for_instance(self, instance):
        raise NotImplementedError


class TrainableQAModel(QAModel, metaclass=abc.ABCMeta):
    """
    This is a version of a QAModel that can be trained on input data.
    """
    def __init__(self, **kwargs):
        super(TrainableQAModel, self).__init__(**kwargs)
        self._save_model_to = self._p['models.save.path']
        if not hasattr(self, "_model"):
            self._model = None
        self._model_number = 0
        if not hasattr(self, "_file_extension"):
            self._file_extension = "model"
        self._model_file_name = "{}_{}.{}".format(self.__class__.__name__, self._model_number, self._file_extension)
        while os.path.exists(self._save_model_to + self._model_file_name):
            self._model_number += 1
            self._model_file_name = "{}_{}.{}".format(self.__class__.__name__, self._model_number, self._file_extension)

    @abc.abstractmethod
    def prepare_model(self, train_tokens, properties_set):
        """
        Method that should override to init objects and parameters that are needed for the model training.
        E.g. vocabulary index.

        :param train_tokens:
        :param properties_set:
        """

    @abc.abstractmethod
    def train(self, data_with_targets, validation_with_targets=None):
        raise NotImplementedError

    @abc.abstractmethod
    def encode_batch(self, graphs, verbose=False):
        raise NotImplementedError

    def encode_data_for_training(self, data_with_targets):
        input_set, targets = data_with_targets
        if self._p.get("loss", 'categorical_crossentropy') == 'categorical_crossentropy':
            targets = keras.utils.np_utils.to_categorical(targets, len(input_set[0][1]))

        sentences_matrix, graph_matrix = self.encode_batch(input_set, verbose=False)
        assert len(sentences_matrix) == len(graph_matrix) == len(targets)
        return sentences_matrix, graph_matrix, targets

    def _preprocess_sentence_tokens(self, sentence_tokens, graph_set):
        if self._p.get("replace.entities", False) and len(graph_set) > 0:
            sentence_tokens = graph.replace_entities({'tokens': sentence_tokens, 'edgeSet': graph_set[0]['edgeSet']})[
                'tokens']
        if self._p.get("mark.sent.boundaries", False):
            sentence_tokens = ["<S>"] + sentence_tokens + ["<E>"]
        return sentence_tokens

    def _get_edge_label(self, edge):
        property_label = graph.get_property_str_representation(edge, wdaccess.property2label, self._p.get("replace.entities", False))
        if self._p.get("mark.sent.boundaries", False):
            property_label = "<S> " + property_label + " <E>"
        return property_label

    @abc.abstractmethod
    def encode_question(self, graph_set):
        raise NotImplementedError

    @abc.abstractmethod
    def encode_graphs(self, graph_set):
        raise NotImplementedError

    @abc.abstractmethod
    def load_from_file(self, path_to_model):
        """
        Load a model from file.

        :param path_to_model: path to the model file.
        """



