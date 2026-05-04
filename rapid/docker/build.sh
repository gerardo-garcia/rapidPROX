#!/bin/bash

docker build -t 127.0.0.1:5000/prox:latest ./prox
docker build -t 127.0.0.1:5000/rapid-controller:latest ./rapid-controller

