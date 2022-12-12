#!/bin/bash

set -e

wget https://github.com/xianyi/OpenBLAS/archive/v0.3.21.tar.gz
tar zxvf v0.3.21.tar.gz && cd OpenBLAS-0.3.21
make NO_STATIC=1 NO_LAPACK=1 NO_LAPACKE=1 NO_AFFINITY=1 USE_OPENMP=1 \
    TARGET=HASWELL DYNAMIC_ARCH=1 \
    NUM_THREADS=64 MAJOR_VERSION=3 libs shared
make PREFIX=/usr/local NUM_THREADS=64 MAJOR_VERSION=3 install
cd ..
rm -rf OpenBLAS-0.3.21 && rm v0.3.21.tar.gz
