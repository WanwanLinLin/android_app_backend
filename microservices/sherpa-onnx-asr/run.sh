#!/bin/bash

export LD_LIBRARY_PATH=/opt/conda/envs/faster-qwen3-tts/lib/python3.12/site-packages/nvidia/cudnn/lib:$LD_LIBRARY_PATH

CUDA_VISIBLE_DEVICES=2 python3 api.py