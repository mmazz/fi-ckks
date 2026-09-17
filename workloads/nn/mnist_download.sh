#!/bin/bash
if [[ ! -d "data" ]]; then
    mkdir data
    cd data
    git clone git@github.com:phoebetronic/mnist.git
    unzip mnist/mnist_test.csv.zip
    unzip mnist/mnist_train.csv.zip
    cd ..
else
    echo "MNIST data already exists."
fi
