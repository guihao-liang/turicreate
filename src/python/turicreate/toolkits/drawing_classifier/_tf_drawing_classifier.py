# -*- coding: utf-8 -*-
# Copyright © 2019 Apple Inc. All rights reserved.
#
# Use of this source code is governed by a BSD-3-clause license that can
# be found in the LICENSE.txt file or at https://opensource.org/licenses/BSD-3-Clause
from __future__ import print_function as _
from __future__ import division as _
from __future__ import absolute_import as _
from turicreate.util import _ProgressTablePrinter
import tensorflow as _tf
import numpy as _np
import time as _time
from .._tf_model import TensorFlowModel
import turicreate.toolkits._tf_utils as _utils

import tensorflow.compat.v1 as _tf
_tf.disable_v2_behavior()


class DrawingClassifierTensorFlowModel(TensorFlowModel):

    def __init__(self, net_params, batch_size, num_classes):
        """
        Defines the TensorFlow model, loss, optimisation and accuracy. Then
        loads the MXNET weights into the model.

        """
        for key in net_params.keys():
            net_params[key] = _utils.convert_shared_float_array_to_numpy(net_params[key])

        _tf.reset_default_graph()

        self.num_classes = num_classes
        self.batch_size = batch_size

        self.input = _tf.placeholder(_tf.float32, [None, 28, 28, 1])
        self.input = _tf.div(self.input, 255.0)
        self.one_hot_labels = _tf.placeholder(_tf.int32, [None, self.num_classes])

        # Weights
        weights = {
        'drawing_conv0_weight' : _tf.Variable(_tf.zeros([3, 3, 1, 16]), name='drawing_conv0_weight'),
        'drawing_conv1_weight' : _tf.Variable(_tf.zeros([3, 3, 16, 32]), name='drawing_conv1_weight'),
        'drawing_conv2_weight' : _tf.Variable(_tf.zeros([3, 3, 32, 64]), name='drawing_conv2_weight'),
        'drawing_dense0_weight': _tf.Variable(_tf.zeros([576, 128]), name='drawing_dense0_weight'),
        'drawing_dense1_weight': _tf.Variable(_tf.zeros([128, self.num_classes]), name='drawing_dense1_weight')
        }

        # Biases
        biases = {
        'drawing_conv0_bias' : _tf.Variable(_tf.zeros([16]), name='drawing_conv0_bias'),
        'drawing_conv1_bias' : _tf.Variable(_tf.zeros([32]), name='drawing_conv1_bias'),
        'drawing_conv2_bias' : _tf.Variable(_tf.zeros([64]), name='drawing_conv2_bias'),
        'drawing_dense0_bias': _tf.Variable(_tf.zeros([128]), name='drawing_dense0_bias'),
        'drawing_dense1_bias': _tf.Variable(_tf.zeros([self.num_classes]), name='drawing_dense1_bias')
        }

        conv_1 = _tf.nn.conv2d(self.input, weights["drawing_conv0_weight"], strides=1, padding='SAME')
        conv_1 = _tf.nn.bias_add(conv_1, biases["drawing_conv0_bias"])
        relu_1 = _tf.nn.relu(conv_1)
        pool_1 = _tf.nn.max_pool2d(relu_1, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME')

        conv_2 = _tf.nn.conv2d(pool_1, weights["drawing_conv1_weight"], strides=1, padding='SAME')
        conv_2 = _tf.nn.bias_add(conv_2, biases["drawing_conv1_bias"])
        relu_2 = _tf.nn.relu(conv_2)
        pool_2 = _tf.nn.max_pool2d(relu_2, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME')

        conv_3 = _tf.nn.conv2d(pool_2, weights["drawing_conv2_weight"], strides=1, padding='SAME')
        conv_3 = _tf.nn.bias_add(conv_3, biases["drawing_conv2_bias"])
        relu_3 = _tf.nn.relu(conv_3)
        pool_3 = _tf.nn.max_pool2d(relu_3, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='VALID')

        # Flatten the data to a 1-D vector for the fully connected layer
        fc1 = _tf.reshape(pool_3, (-1, 576))

        fc1 = _tf.nn.xw_plus_b(fc1, weights=weights["drawing_dense0_weight"],
            biases=biases["drawing_dense0_bias"])

        fc1 = _tf.nn.relu(fc1)

        out = _tf.nn.xw_plus_b(fc1, weights=weights["drawing_dense1_weight"],
            biases=biases["drawing_dense1_bias"])
        out = _tf.nn.softmax(out)

        self.predictions = out

        # Loss
        self.cost = _tf.reduce_mean(_tf.nn.softmax_cross_entropy_with_logits_v2(logits=self.predictions,
            labels=self.one_hot_labels))

        # Optimizer
        self.optimizer = _tf.train.AdamOptimizer(learning_rate=0.001).minimize(self.cost)

        # Predictions
        correct_prediction = _tf.equal(_tf.argmax(self.predictions, 1), _tf.argmax(self.one_hot_labels, 1))
        self.accuracy = _tf.reduce_mean(_tf.cast(correct_prediction, _tf.float32))

        self.sess = _tf.Session()
        self.sess.run(_tf.global_variables_initializer())

        # Assign the initialised weights from MXNet to tensorflow
        layers = ['drawing_conv0_weight', 'drawing_conv0_bias', 'drawing_conv1_weight', 'drawing_conv1_bias',
        'drawing_conv2_weight', 'drawing_conv2_bias', 'drawing_dense0_weight', 'drawing_dense0_bias',
        'drawing_dense1_weight', 'drawing_dense1_bias']

        for key in layers:
            if 'bias' in key:
                self.sess.run(_tf.assign(_tf.get_default_graph().get_tensor_by_name(key+":0"),
                    net_params[key]))
            else:
                if 'dense' in key:
                    dense_weights = _utils.convert_dense_coreml_to_tf(net_params[key])
                    self.sess.run(_tf.assign(_tf.get_default_graph().get_tensor_by_name(key+":0"),
                        dense_weights))
                else:
                    # TODO: Call _utils.convert_conv2d_coreml_to_tf when #2513 is merged
                    self.sess.run(_tf.assign(_tf.get_default_graph().get_tensor_by_name(key+":0"),
                                        _np.transpose(net_params[key], (2, 3, 1, 0))))


    def train(self, feed_dict):

        for key in feed_dict.keys():
            feed_dict[key] = _utils.convert_shared_float_array_to_numpy(feed_dict[key])

        num_samples = float(feed_dict["num_samples"])
        one_hot_labels = _np.zeros((int(num_samples), self.num_classes))

        # convert to one hot
        labels = feed_dict["labels"].astype("int32").T
        one_hot_labels[_np.arange(int(num_samples)), labels] = 1

        _, final_train_loss, final_train_accuracy = self.sess.run(
            [self.optimizer, self.cost, self.accuracy],
                            feed_dict={
                                self.input: feed_dict['input'],
                                self.one_hot_labels: one_hot_labels
                            })
        result = {'accuracy' : _np.array(final_train_accuracy),
                  'loss' : _np.array(final_train_loss)}
        return result


    def predict(self, feed_dict):

        is_train = ("labels" in feed_dict)

        for key in feed_dict.keys():
            feed_dict[key] = _utils.convert_shared_float_array_to_numpy(
                feed_dict[key])

        num_samples = float(feed_dict["num_samples"])
        one_hot_labels = _np.zeros((int(num_samples), self.num_classes))

        feed_dict_for_session = { self.input: feed_dict["input"] }

        if is_train:
            # convert to one hot
            labels = feed_dict["labels"].astype("int32").T
            one_hot_labels[_np.arange(num_samples), labels] = 1
            feed_dict_for_session[self.one_hot_labels] = one_hot_labels
            pred_probs, loss, final_accuracy = self.sess.run(
                [self.predictions, self.cost, self.accuracy],
                feed_dict=feed_dict_for_session)
            result = {'accuracy' : _np.array(final_accuracy),
                      'loss': _np.array(loss),
                      'output' : _np.array(pred_probs)}
        else:
            pred_probs = self.sess.run([self.predictions],
                feed_dict=feed_dict_for_session)
            result = {'output' : _np.array(pred_probs)}

        return result


    def export_weights(self):
        """
        Retrieve weights from the TF model, convert to the format Core ML
        expects and store in a dictionary.

        Returns
        -------
        net_params : dict
            Dictionary of weights, where the key is the name of the
            layer (e.g. `drawing_conv0_weight`) and the value is the
            respective weight of type `numpy.ndarray`.
        """

        from pprint import pprint as pprint
        net_params = {}
        layer_names = _tf.trainable_variables()
        layer_weights = self.sess.run(layer_names)
        ff = open("/Users/guihaoliang/tf_dc_weights.txt", 'w') #as f:
        #    from pprint import pprint as pprint
        #    pprint(, f)

        for var, val in zip(layer_names, layer_weights):
            if 'bias' in var.name:
                pprint("{} ".format(var.name), ff)
                pprint(val, ff)
                net_params.update({var.name.replace(":0", ""): val})
            else:
                if 'dense' in var.name:
                    pprint("{} ".format(var.name), ff)
                    pprint(val.shape, ff)
                    pprint(val, ff)
                    net_params.update(
                        {var.name.replace(":0", ""): _utils.convert_dense_tf_to_coreml(val)})
                else:
                    # TODO: Call _utils.convert_conv2d_tf_to_coreml once #2513 is merged.
                    pprint("{} ".format(var.name), ff)
                    pprint(val.shape, ff)
                    pprint(val, ff)
                    net_params.update(
                        {var.name.replace(":0", ""): _np.transpose(val, (3, 2, 0, 1))})

        with open("/Users/guihaoliang/tf_dc.txt", 'w') as f:
            for k in net_params.keys():
                pprint(k, f)
                pprint(net_params[k].shape, f)
                pprint(net_params[k], f)

        return net_params
