"""Milvus Server
"""
from argparse import ArgumentParser
import logging
import os
import shutil
import signal
import sys
import lzma
from os import makedirs
from os.path import join, abspath, dirname, expandvars, isfile
import re
import subprocess
import socket
from time import sleep
from typing import Any, List

__version__ = '2.2.3'


LOGGERS = {}


def _initialize_data_files() -> None:
    bin_dir = join(dirname(abspath(__file__)), 'data', 'bin')
    files = [file[:-5]
             for file in os.listdir(bin_dir) if file.endswith('.lzma')]
    files = [file for file in files if not isfile(
        join(bin_dir, file)) or os.stat(join(bin_dir, file)).st_size < 10]
    for file in files:
        with lzma.LZMAFile(join(bin_dir, f'{file}.lzma'), mode='r') as lzma_file:
            with open(join(bin_dir, file), 'wb') as raw:
                raw.write(lzma_file.read())
                os.chmod(join(bin_dir, file), 0o755)


def _create_logger(usage: str = 'null') -> logging.Logger:
    usage = usage.lower()
    if usage in LOGGERS:
        return LOGGERS[usage]
    logger = logging.Logger(name=f'python_milvus_server_{usage}')
    if usage != 'debug':
        logger.setLevel(logging.FATAL)
    else:
        logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d: %(message)s')
        logger.addHandler(handler)
        handler.setFormatter(formatter)
    LOGGERS[usage] = logger
    return logger


class MilvusServerConfig:
    RANDOM_PORT_START = 40000

    def __init__(self, **kwargs):
        """create new configuration for milvus server

        Kwargs:
            template(str, optional): template file path

            data_dir(str, optional): base data directory for log and data
        """
        self.base_data_dir = ''
        self.configs: dict = kwargs
        self.logger = _create_logger(
            'debug' if kwargs.get('debug', False) else 'null')

        self.template_file: str = kwargs.get('template', None)
        self.template_text: str = ''
        self.config_key_maps = {}
        self.configurable_items = {}
        self.load_template()
        self.parse_template()
        self.listen_ports = {}

    def update(self, **kwargs):
        """ update configs
        """
        self.configs.update(kwargs)

    def load_template(self):
        """ load config template for milvus server
        """
        if not self.template_file:
            self.template_file = join(
                dirname(abspath(__file__)), 'data', 'config.yaml.template')
        with open(self.template_file, 'r', encoding='utf-8') as template:
            self.template_text = template.read()

    def parse_template(self):
        """ parse template, lightweight template engine for avoid introducing dependencies like: yaml/Jinja2

        We using:
        - {{ foo }} for variable
        - {{ bar: value }} for variable with default values
        - {{ bar(type) }} and {{ bar(type): value }} for type hint
        """
        for line in self.template_text.split('\n'):
            matches = re.match(r'.*\{\{(.*)}}.*', line)
            if matches:
                text = matches.group(1)
                original_key = '{{' + text + '}}'
                text = text.strip()
                value_type = str
                if ':' in text:
                    key, val = text.split(':', maxsplit=2)
                    key, val = key.strip(), val.strip()
                else:
                    key, val = text.strip(), None
                if '(' in key:
                    key, type_str = key.split('(')
                    key, type_str = key.strip(), type_str.strip().replace(')', '')
                    value_type = eval(type_str)
                self.config_key_maps[original_key] = key
                self.configurable_items[key] = [
                    value_type, self.get_value(val, value_type)]
        self.verbose_configurable_items()

    def verbose_configurable_items(self):
        for key, val in self.configurable_items.items():
            self.logger.debug(
                'Configurable item %s(%s) with default: %s', key, val[0], val[1])

    def resolve(self):
        self.cleanup_listen_ports()
        self.resolve_all_listen_ports()
        self.resolve_storage()
        for key, value in self.configurable_items.items():
            if value[1] is None:
                raise RuntimeError(
                    f'{key} is still not resolved, please try specify one.')
        # ready to start
        self.cleanup_listen_ports()
        self.write_config()
        self.verbose_configurable_items()

    def resolve_all_listen_ports(self):
        port_keys = list(filter(lambda x: x.endswith(
            '_port'), self.configurable_items.keys()))
        for port_key in port_keys:
            if port_key in self.configs:
                port = int(self.configs.get(port_key))
                sock = self.try_bind_port(port)
                if not sock:
                    raise RuntimeError(
                        f'set {port_key}={port}, but seems you could not bind it')
                else:
                    self.logger.debug(
                        'bind port %d success, using it as %s', port, port_key)
                self.listen_ports[port_key] = (port, sock)
            else:
                port_start = self.configurable_items[port_key][1] or self.RANDOM_PORT_START
                port_start = int(port_start)
                for i in range(10000):
                    port = port_start + i
                    sock = self.try_bind_port(port)
                    if sock:
                        self.listen_ports[port_key] = (port, sock)
                        self.logger.debug(
                            'bind port %d success, using it as %s', port, port_key)
                        break
        for port_key, data in self.listen_ports.items():
            self.configurable_items[port_key][1] = data[0]

    @classmethod
    def try_bind_port(cls, port):
        """ return a socket if bind success, else None
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(('127.0.0.1', port))
            sock.listen()
            return sock
        except Exception as ex:
            pass
        return None

    @classmethod
    def get_default_data_dir(cls):
        if sys.platform.lower() == 'win32':
            default_dir = expandvars('%APPDATA%')
            return join(default_dir, 'milvus.io', 'milvus-server')
        default_dir = expandvars('${HOME}')
        return join(default_dir, '.milvus.io', 'milvus-server')

    @classmethod
    def get_value_text(cls, val) -> str:
        if isinstance(val, bool):
            return 'true' if val else 'false'
        return str(val)

    @classmethod
    def get_value(cls, text, val_type) -> Any:
        if val_type == bool:
            return True if text == 'true' else False
        if val_type == int:
            if not text:
                return 0
            return int(text)
        return text

    def resolve_storage(self):
        self.base_data_dir = self.configs.get(
            'data_dir', self.get_default_data_dir())
        self.base_data_dir = abspath(self.base_data_dir)
        makedirs(self.base_data_dir, exist_ok=True)
        config_dir = join(self.base_data_dir, 'configs')
        logs_dir = join(self.base_data_dir, 'logs')
        storage_dir = join(self.base_data_dir, 'data')
        for subdir in (config_dir, logs_dir, storage_dir):
            makedirs(subdir, exist_ok=True)

        # logs
        if sys.platform.lower() == 'win32':
            self.set('etcd_log_path', 'winfile:///' +
                     join(logs_dir, 'etcd.log').replace('\\', '/'))
        else:
            self.set('etcd_log_path', join(logs_dir, 'etcd.log'))
        self.set('system_log_path', logs_dir)

        # data
        self.set('etcd_data_dir', join(storage_dir, 'etcd.data'))
        self.set('local_storage_dir', join(storage_dir, 'storage'))
        self.set('rocketmq_data_dir', join(storage_dir, 'rocketmq'))

    def get(self, attr) -> Any:
        return self.configurable_items[attr][1]

    def get_type(self, attr) -> Any:
        return self.configurable_items[attr][0]

    def set(self, attr, val) -> None:
        if type(val) == self.configurable_items[attr][0]:
            self.configurable_items[attr][1] = val

    def cleanup_listen_ports(self):
        for data in self.listen_ports.values():
            if data[1]:
                data[1].close()
        self.listen_ports.clear()

    def write_config(self):
        config_file = join(self.base_data_dir, 'configs', 'milvus.yaml')
        content = self.template_text
        for key, val in self.config_key_maps.items():
            value = self.configurable_items[val][1]
            value_text = self.get_value_text(value)
            content = content.replace(key, value_text)
        with open(config_file, 'w', encoding='utf-8') as config:
            config.write(content)


class MilvusServer:
    def __init__(self, config: MilvusServerConfig = None, **kwargs):
        """_summary_

        Args:
            config (MilvusServerConfig, optional): the server config. Defaults to default_server_config.

        Kwargs:
        """
        if not config:
            self.config = MilvusServerConfig()
        else:
            self.config = config
        self.config.update(**kwargs)
        self.server_proc = None
        self.proc_fds = {}
        self._debug = kwargs.get('debug', False)
        self.logger = _create_logger('debug' if self._debug else 'null')

    @classmethod
    def get_milvus_executable_path(cls):
        """ get where milvus
        """
        if sys.platform.lower() == 'win32':
            return join(dirname(abspath(__file__)), 'data', 'bin', 'milvus.exe')
        return join(dirname(abspath(__file__)), 'data', 'bin', 'milvus')

    def __enter__(self):
        self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def __del__(self):
        self.stop()

    @classmethod
    def prepend_path_to_envs(cls, envs, name, val):
        envs.update({name: ':'.join([val, os.environ.get(name, '')])})

    def cleanup(self):
        if self.running:
            raise RuntimeError('Server is running')
        shutil.rmtree(self.config.base_data_dir, ignore_errors=True)

    def wait(self):
        while self.running:
            sleep(0.1)

    def start(self):
        self.config.resolve()
        milvus_exe = self.get_milvus_executable_path()
        old_pwd = os.getcwd()
        os.chdir(self.config.base_data_dir)
        envs = os.environ.copy()
        envs.update({'DEPLOY_MODE': 'STANDALONE'})
        if sys.platform.lower() == 'linux':
            self.prepend_path_to_envs(
                envs, 'LD_LIBRARY_PATH', dirname(milvus_exe))
        if sys.platform.lower() == 'darwin':
            self.prepend_path_to_envs(
                envs, 'DYLD_LIBRARY_PATH', dirname(milvus_exe))
        for name in ('stdout', 'stderr'):
            self.proc_fds[name] = open(
                join(self.config.base_data_dir, 'logs', f'milvus-{name}.log'), 'w')
        if self._debug:
            self.server_proc = subprocess.Popen(
                [milvus_exe, 'run', 'standalone'],
                env=envs)
        else:
            self.server_proc = subprocess.Popen(
                [milvus_exe, 'run', 'standalone'],
                stdout=self.proc_fds['stdout'],
                stderr=self.proc_fds['stderr'],
                env=envs)
        os.chdir(old_pwd)

    def stop(self):
        if self.server_proc:
            self.server_proc.terminate()
            self.server_proc.wait()
            self.server_proc = None
        for fd in self.proc_fds.values():
            fd.close()
        self.proc_fds.clear()

    def set_base_dir(self, dir_path):
        self.config.configs.update(data_dir=dir_path)
        self.config.resolve_storage()

    @property
    def running(self) -> bool:
        return self.server_proc is not None

    @property
    def server_address(self) -> str:
        return '127.0.0.1'

    @property
    def config_keys(self) -> List[str]:
        return self.config.configurable_items.keys()

    @property
    def listen_port(self) -> int:
        return int(self.config.get('proxy_port'))

    @listen_port.setter
    def listen_port(self, val: int):
        self.config.set('proxy_port', val)

    @property
    def debug(self):
        return self._debug

    @debug.setter
    def debug(self, val: bool):
        self._debug = val
        self.logger = _create_logger('debug' if val else 'null')
        self.config.logger = self.logger


_initialize_data_files()
default_server = MilvusServer()
debug_server = MilvusServer(MilvusServerConfig(), debug=True)


def main():
    parser = ArgumentParser()
    parser.add_argument('--debug', action='store_true',
                        dest='debug', default=False, help='enable debug')
    parser.add_argument('--data', dest='data_dir', default='',
                        help='set base data dir for milvus')

    # dynamic configurations
    for key in default_server.config_keys:
        val = default_server.config.get(key)
        if val is not None:
            val_type = default_server.config.get_type(key)
            name = '--' + key.replace('_', '-')
            parser.add_argument(name, type=val_type, default=val,
                                dest=f'x_{key}', help=f'set value for {key} ({val_type.__name__})')

    args = parser.parse_args()

    # select server
    server = debug_server if args.debug else default_server

    # set base dir if configured
    if args.data_dir:
        server.set_base_dir(args.data_dir)

    # apply configs
    for name, value in args._get_kwargs():
        if name.startswith('x_'):
            server.config.set(name[2:], value)

    signal.signal(signal.SIGINT, lambda sig, h: server.stop())

    server.start()
    server.wait()


if __name__ == '__main__':
    main()
