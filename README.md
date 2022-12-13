# Python Milvus Server

[![PyPI Version](https://img.shields.io/pypi/v/python-milvus-server.svg)](https://pypi.python.org/pypi/python-milvus-server)

Milvus server started by python

Currently, windows/linux with x86_64 is supported.

## Installation

You could simply install it with pip:

```
pip install python-milvus-server
```

or with a specific version
```
pip install python-milvus-server~=2.2.0
```

or install it from the source.

### Install from source

#### Windows

Currently, Milvus windows is build with MSYS2, so please follow below steps for build and install this Milvus server for windows.

- Install MSYS2, currently please use **msys2-base-x86_64-20220603**, which could be found at [MSYS2 Install Release](https://github.com/msys2/msys2-installer/releases/tag/2022-06-03)
- In MINGW64 console, run the prebuild scripts: `sh run-prebuild.sh`, after that, you could find all needed dll files under folder `milvus/bin`
- Using setup.py to install `python-milvus-server`
  - `python setup.py install` to install it.
  - `python setup.py bdist_wheel` to build binary package (wheel and setuptools is required).

### Linux

Currently, compile milvus on linux requires install some dependencies, so we create a docker for build the milvus executable.

- On any linux with python3 installed, docker is installed and started.
- run the prebuild scripts: `bash run-prebuild.sh`, after that, you should find all needed binaries under folder `milvus/bin`
- Using setup.py to install `python-milvus-server`
  - `python setup.py install` to install it.
  - `python setup.py bdist_wheel` to build binary package (wheel and setuptools is required).

## Usage

You could load the `default_server` and start it.

```python
from milvus_server import default_server
from pymilvus import connections

# Optional, if you want store all related data to specific location
# default it wil using:
#   %APPDATA%/milvus-io/milvus-server on windows
#   ~/.milvus-io/milvus-server on linux
default_server.set_base_dir('D:\\test_milvus')

# Optional, if you want cleanup previous data
default_server.cleanup()

# star you milvus server
default_server.start()

# Now you could connect with localhost and the port
# The port is in default_server.listen_port
connections.connect(host='127.0.0.1', port=default_server.listen_port)

```

You could see [example.py](examples/example.py) for a full example.

## Some advanced topic

### Debug startup

You could use `debug_server` instead of `default_server` for checking startup failures.

```python
from milvus_server import debug_server
```

and you could also try create server instance by your self

```python
from milvus_server import MilvusServer

server = MilvusServer(debug=True)
```

### Multiple instance

Yes, we support multiple milvus server instance. Currently windows only(due to pid file path is hardcoded on linux)
note: as by default they're using the same data dir, you set different data dir for each instances

```python
from milvus_server import MilvusServer

server1 = MilvusServer()
server2 = MilvusServer()

# this is mandatory
server1.set_base_dir('d:\\test_1')
server2.set_base_dir('d:\\test_2')

```

### Context

You could close server while you not need it anymore.
Or, you're able to using `with` context to start/stop it.
```python
from milvus_server import default_server

with default_server:
    # milvus started, using default server here
    ...
```
