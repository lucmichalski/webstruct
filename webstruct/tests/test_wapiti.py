# -*- coding: utf-8 -*-
from __future__ import absolute_import
import os
import unittest
import pickle
import tempfile

import webstruct
from webstruct.features import EXAMPLE_TOKEN_FEATURES
from webstruct.metrics import bio_classification_report
from webstruct.wapiti import WapitiCRF, create_wapiti_pipeline
from webstruct.utils import train_test_split_noshuffle
from webstruct.model import NER
from .utils import get_trees, DATA_PATH

class WapitiTest(unittest.TestCase):

    TAGSET = ['ORG', 'CITY', 'STREET', 'ZIPCODE', 'STATE', 'TEL', 'FAX']

    def _get_Xy(self, num, bilou=False):
        trees = get_trees(num)
        html_tokenizer = webstruct.HtmlTokenizer(tagset=self.TAGSET, bilou=bilou)
        return html_tokenizer.tokenize(trees)

    def _get_train_test(self, train_size, test_size, bilou=False):
        X, y = self._get_Xy(train_size+test_size, bilou)
        return train_test_split_noshuffle(X, y, test_size=test_size)

    def get_pipeline(self, **kwargs):
        params = dict(
            token_features=EXAMPLE_TOKEN_FEATURES,
            verbose=False,
            top_n=5,
        )
        params.update(kwargs)
        return create_wapiti_pipeline(**params)

    def test_training_tagging(self):
        X_train, X_test, y_train, y_test = self._get_train_test(8, 2)

        # Train the model:
        model = self.get_pipeline()
        model.fit(X_train, y_train)

        # Model should learn something:
        #
        # y_pred = model.predict(X_test)
        # print(bio_classification_report(y_test, y_pred))
        assert model.score(X_test, y_test) > 0.3

    # def test_training_tagging_bilou(self):
    ## fails because the model does not learn
    #     X_train, X_test, y_train, y_test = self._get_train_test(8, 2,
    #                                                             bilou=True)
    #
    #     # Train the model:
    #     model = self.get_pipeline()
    #     model.fit(X_train, y_train)
    #     # print('\nX_train: {}\n\ny_train: {}'.format(X_train, y_train))
    #     # Model should learn something:
    #
    #     y_pred = model.predict(X_test)
    #     print(bio_classification_report(y_test, y_pred))
    #     assert model.score(X_test, y_test) > 0.3

    # def test_devdata(self):
    ## Error with X_dev format passed to  sklearn
    #     X_train, X_dev, y_train, y_dev = self._get_train_test(8, 4)
    #     model = self.get_pipeline()
    #     # print('X_dev: ', X_dev)
    #     # print('y_dev: ', y_dev)
    #     model.fit(X_train, y_train, X_dev=X_dev, y_dev=y_dev)
    #     # assert model.crf.training_log_.featgen_num_features > 100
    #     # assert model.crf.training_log_.last_iteration['avg_f1'] > 0.3
    #
    #     self.assertRaises(ValueError, model.fit, X_train, y_train, X_dev=X_dev)
    #     self.assertRaises(ValueError, model.fit, X_train, y_train, y_dev=y_dev)

    def test_pickle(self):
        ## fails because pipeline in wapiti is built different from crfsuite
        X_train, X_test, y_train, y_test = self._get_train_test(8, 2)

        model = self.get_pipeline()
        model.fit(X_train, y_train)
        score = model.score(X_test, y_test)
        assert score > 0.3

        data = pickle.dumps(model, pickle.HIGHEST_PROTOCOL)
        filename = model.steps[-1][1].modelfile.name

        # make sure model file is gone
        del model
        try:
            os.unlink(filename)
        except OSError:
            pass

        # model should work after unpickling
        model2 = pickle.loads(data)
        score2 = model2.score(X_test, y_test)
        assert score2 > 0.3
        assert abs(score2-score) < 1e-6

    def test_explicit_modelname(self):
        X_train, X_test, y_train, y_test = self._get_train_test(8, 2)

        # pass a custom model_filename to the constructor
        _, fname = tempfile.mkstemp('.crfsuite', 'tst-model-')
        model = self.get_pipeline(model_filename=fname)
        model.fit(X_train, y_train)

        self.assertFalse(model.crf.modelfile.auto)
        self.assertEqual(model.crf.modelfile.name, fname)

        # the file should be preserved when the model is closed
        del model
        self.assertTrue(os.path.isfile(fname))

        # we shouldn't need to train the model again
        model2 = self.get_pipeline(model_filename=fname)
        assert model2.score(X_test, y_test) > 0.3

        # and it should work after pickling/unpickling
        dump = pickle.dumps(model2, pickle.HIGHEST_PROTOCOL)

        assert model2.score(X_test, y_test) > 0.3
        self.assertTrue(os.path.isfile(fname))

        model3 = pickle.loads(dump)
        assert model3.score(X_test, y_test) > 0.3
        self.assertTrue(os.path.isfile(fname))
        self.assertEqual(model3.steps[-1][1].modelfile.name, fname)

        # cleanup
        os.unlink(fname)

    def test_wapiti(self):
        X, y = self._get_Xy(10)
        model = self.get_pipeline()
        model.fit(X, y)

        ner = NER(model)

        # Load 7.html file - model is trained on it, so
        # the prediction should work well.
        with open(os.path.join(DATA_PATH, '7.html'), 'rb') as f:
            html = f.read()

        groups = ner.extract_groups(html, dont_penalize={'TEL', 'FAX'})
        group1 = [
            (u'4503 W. Lovers Lane', 'STREET'),
            (u'Dallas', 'CITY'),
            (u'TX', 'STATE'),
            (u'75206', 'ZIPCODE'),
            (u'214-351-2456', 'TEL'),
            (u'214-904-1716', 'FAX'),
        ]
        group2 = [
            (u'4515 W. Lovers Lane', 'STREET'),
            (u'Dallas', 'CITY'),
            (u'TX', 'STATE'),
            (u'75206', 'ZIPCODE'),
            (u'214-352-0031', 'TEL'),
            (u'214-350-5302', 'FAX')
        ]
        self.assertIn(group1, groups)
        self.assertIn(group2, groups)

        # pickle/unpickle NER instance
        dump = pickle.dumps(ner, pickle.HIGHEST_PROTOCOL)
        ner2 = pickle.loads(dump)

        self.assertNotEqual(
            ner.model.steps[-1][1].modelfile.name,
            ner2.model.steps[-1][1].modelfile.name,
        )

        groups = ner2.extract_groups(html, dont_penalize={'TEL', 'FAX'})
        self.assertIn(group1, groups)
        self.assertIn(group2, groups)

    def test_ner_bilou(self):
        X, y = self._get_Xy(10, bilou=True)
        model = self.get_pipeline()
        model.fit(X, y)

        ner = NER(model, bilou=True)

        # Load 7.html file - model is trained on it, so
        # the prediction should work well.
        with open(os.path.join(DATA_PATH, '7.html'), 'rb') as f:
            html = f.read()

        groups = ner.extract_groups(html, dont_penalize={'TEL', 'FAX'})
        group1 = [
            (u'4503 W. Lovers Lane', 'STREET'),
            (u'Dallas', 'CITY'),
            (u'TX', 'STATE'),
            (u'75206', 'ZIPCODE'),
            (u'214-351-2456', 'TEL'),
            (u'214-904-1716', 'FAX'),
        ]
        group2 = [
            (u'4503 W. Lovers Lane', 'STREET'),
            (u'Dallas', 'CITY'),
            (u'TX', 'STATE'),
            (u'75206', 'ZIPCODE'),
            (u'214-351-2456', 'TEL'),
            (u'214-904-1716', 'FAX')
        ]
        self.assertIn(group1, groups)
        self.assertIn(group2, groups)
        # pickle/unpickle NER instance
        dump = pickle.dumps(ner, pickle.HIGHEST_PROTOCOL)
        ner2 = pickle.loads(dump)

        self.assertNotEqual(
            ner.model.steps[-1][1].modelfile.name,
            ner2.model.steps[-1][1].modelfile.name,
        )

        groups = ner2.extract_groups(html, dont_penalize={'TEL', 'FAX'})
        self.assertIn(group1, groups)
        self.assertIn(group2, groups)
