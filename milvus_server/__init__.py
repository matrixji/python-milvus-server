"""Milvus Server
"""
import logging
import os
import shutil
import sys
import lzma
from os import makedirs
from os.path import join, abspath, dirname, expandvars, isfile
import re
import subprocess
import socket

LOGGERS = {}


def _initialize_data_files():
    bin_dir = join(dirname(abspath(__file__)), 'data', 'bin')
    files = [file[:-5] for file in os.listdir(bin_dir) if file.endswith('.lzma')]
    files = [file for file in files if not isfile(join(bin_dir, file)) or os.stat(join(bin_dir, file)).st_size < 10]
    for file in files:
        with lzma.LZMAFile(join(bin_dir, f'{file}.lzma'), mode='r') as lzma_file:
            with open(join(bin_dir, file), 'wb') as raw:
                raw.write(lzma_file.read())
                os.chmod(join(bin_dir, file), 0o755)


def create_logger(usage: str = 'null'):
    usage = usage.lower()
    if usage in LOGGERS:
        return LOGGERS[usage]
    logger = logging.Logger(name=f'python_milvus_server_{usage}')
    if usage != 'debug':
        logger.setLevel(logging.FATAL)
    else:
        logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d: %(message)s')
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
        self.base_data_dir = None
        self.configs: dict = kwargs
        self.logger = create_logger('debug' if kwargs.get('debug', False) else 'null')

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
            self.template_file = join(dirname(abspath(__file__)), 'data', 'config.yaml.template')
        with open(self.template_file, 'r', encoding='utf-8') as template:
            self.template_text = template.read()

    def parse_template(self):
        """ parse template, lightweight template engine for avoid introducing dependencies like: yaml/Jinja2

        We using {{ foo }} for variable and {{ bar: value }} for variable with default values
        """
        for line in self.template_text.split('\n'):
            matches = re.match(r'.*\{\{(.*)}}.*', line)
            if matches:
                text = matches.group(1)
                original_key = '{{' + text + '}}'
                text = text.strip()
                if ':' in text:
                    key, val = text.split(':', maxsplit=2)
                    key, val = key.strip(), val.strip()
                else:
                    key, val = text.strip(), None
                self.config_key_maps[original_key] = key
                self.configurable_items[key] = val
        self.verbose_configurable_items()

    def verbose_configurable_items(self):
        for key, val in self.configurable_items.items():
            self.logger.debug('Configurable item %s with default: %s', key, val)

    def resolve(self):
        self.cleanup_listen_ports()
        self.resolve_all_listen_ports()
        self.resolve_storage()
        for key, value in self.configurable_items.items():
            if value is None:
                raise RuntimeError(f'{key} is still not resolved, please try specify one.')
        # ready to start
        self.cleanup_listen_ports()
        self.write_config()
        self.verbose_configurable_items()

    def resolve_all_listen_ports(self):
        port_keys = list(filter(lambda x: x.endswith('_port'), self.configurable_items.keys()))
        for port_key in port_keys:
            if port_key in self.configs:
                port = int(self.configs.get(port_key))
                sock = self.try_bind_port(port)
                if not sock:
                    raise RuntimeError(f'set {port_key}={port}, but seems you could not bind it')
                else:
                    self.logger.debug('bind port %d success, using it as %s', port, port_key)
                self.listen_ports[port_key] = (port, sock)
            else:
                port_start = self.configurable_items[port_key] or self.RANDOM_PORT_START
                port_start = int(port_start)
                for i in range(10000):
                    port = port_start + i
                    sock = self.try_bind_port(port)
                    if sock:
                        self.listen_ports[port_key] = (port, sock)
                        self.logger.debug('bind port %d success, using it as %s', port, port_key)
                        break
        for port_key, data in self.listen_ports.items():
            self.configurable_items[port_key] = data[0]

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

    def resolve_storage(self):
        self.base_data_dir = self.configs.get('data_dir', self.get_default_data_dir())
        self.base_data_dir = abspath(self.base_data_dir)
        makedirs(self.base_data_dir, exist_ok=True)
        config_dir = join(self.base_data_dir, 'configs')
        logs_dir = join(self.base_data_dir, 'logs')
        storage_dir = join(self.base_data_dir, 'data')
        for subdir in (config_dir, logs_dir, storage_dir):
            makedirs(subdir, exist_ok=True)

        # logs
        if sys.platform.lower() == 'win32':
            self.configurable_items['etcd_log_path'] = 'winfile:///' + join(logs_dir, 'etcd.log').replace('\\', '/')
        else:
            self.configurable_items['etcd_log_path'] = join(logs_dir, 'etcd.log')
        self.configurable_items['proxy_log_dir'] = logs_dir
        self.configurable_items['proxy_log_name'] = 'proxy.log'
        self.configurable_items['system_log_path'] = join(logs_dir, 'system.log')

        # data
        self.configurable_items['etcd_data_dir'] = join(storage_dir, 'etcd.data')
        self.configurable_items['local_storage_dir'] = join(storage_dir, 'storage')
        self.configurable_items['rocketmq_data_dir'] = join(storage_dir, 'rocketmq')

    def cleanup_listen_ports(self):
        for data in self.listen_ports.values():
            if data[1]:
                data[1].close()
        self.listen_ports.clear()

    def write_config(self):
        config_file = join(self.base_data_dir, 'configs', 'milvus.yaml')
        content = self.template_text
        for key, val in self.config_key_maps.items():
            value = self.configurable_items[val]
            if isinstance(value, str):
                value_text = "'" + value + "'"
            else:
                value_text = str(value)
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
        self.logger = create_logger('debug' if self._debug else 'null')

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

    def cleanup(self):
        if self.running:
            raise RuntimeError('Server is running')
        shutil.rmtree(self.config.base_data_dir, ignore_errors=True)

    def start(self):
        self.config.resolve()
        milvus_exe = self.get_milvus_executable_path()
        old_pwd = os.getcwd()
        os.chdir(self.config.base_data_dir)
        envs = os.environ.copy()
        envs.update({'DEPLOY_MODE': 'STANDALONE'})
        if sys.platform.lower() == 'linux':
            envs.update({'LD_LIBRARY_PATH': f'{dirname(milvus_exe)}:{os.environ.get("LD_LIBRARY_PATH")}'})
        if sys.platform.lower() == 'darwin':
            envs.update({'DYLD_LIBRARY_PATH': f'{dirname(milvus_exe)}:{os.environ.get("DYLD_LIBRARY_PATH")}'})
        for name in ('stdout', 'stderr'):
            self.proc_fds[name] = open(join(self.config.base_data_dir, 'logs', f'milvus-{name}.log'), 'w')
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
    def listen_port(self) -> int:
        return int(self.config.configurable_items.get('proxy_port'))

    @property
    def debug(self):
        return self._debug

    @debug.setter
    def debug(self, val: bool):
        self._debug = val
        self.logger = create_logger('debug' if val else 'null')
        self.config.logger = create_logger('debug' if val else 'null')


_initialize_data_files()
default_server = MilvusServer()
debug_server = MilvusServer(MilvusServerConfig(), debug=True)
