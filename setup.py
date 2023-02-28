import os
import pathlib
import shutil
import sys
from datetime import datetime
from distutils.command.build import build
from distutils.core import setup
from os import makedirs, listdir, environ
from os.path import join, abspath, dirname, isfile, islink


def get_package_version():
    base_version = '2.2.0'
    if 'MILVUS_SERVER_VERSION' in environ:
        return environ['MILVUS_SERVER_VERSION']
    return f'{base_version}.dev{datetime.now().strftime("%Y%m%d%H%M")}'


def guess_plat_name():
    if 'MILVUS_SERVER_PLATFORM' in environ:
        return environ['MILVUS_SERVER_PLATFORM']
    if sys.platform.lower() == 'darwin':
        return 'macosx_11_0_arm64'
    if sys.platform.lower() == 'linux':
        return 'manylinux2014_x86_64'
    if sys.platform.lower() == 'win32':
        return 'win-amd64'


class CustomBuild(build):

    @classmethod
    def lzma_compress(cls, dest_filepath):
        try:
            import lzma
            os.chmod(dest_filepath, 0o755)
            with open(dest_filepath, 'rb') as raw:
                with lzma.LZMAFile(dest_filepath + '.lzma', mode='w') as lzma_file:
                    lzma_file.write(raw.read())
            with open(dest_filepath, 'wb') as raw:
                raw.write(b'stub')
        except ImportError:
            pass

    @classmethod
    def copy_bin_data(cls):
        milvus_server_bin_dir = join(
            dirname(abspath(__file__)), 'milvus', 'bin')
        dest_bin_dir = join(dirname(abspath(__file__)),
                            'milvus_server', 'data', 'bin')
        shutil.rmtree(dest_bin_dir, ignore_errors=True)
        makedirs(dest_bin_dir, exist_ok=True)
        for filename in listdir(milvus_server_bin_dir):
            filepath = join(milvus_server_bin_dir, filename)
            ext_name = filepath.rsplit('.')[-1]
            dest_filepath = join(dest_bin_dir, filename)
            if isfile(filepath):
                shutil.copy(filepath, dest_filepath, follow_symlinks=False)
            if ext_name != 'lzma':
                try:
                    if not islink(dest_filepath):
                        cls.lzma_compress(dest_filepath)
                except RuntimeError:
                    pass

    def run(self):
        self.copy_bin_data()
        build.run(self)


setup(name='python-milvus-server',
      version=get_package_version(),
      description='Python Milvus Server',
      long_description=(pathlib.Path(__file__).parent /
                        'README.md').read_text(),
      long_description_content_type='text/markdown',
      author='Ji Bin',
      author_email='matrixji@live.com',
      url='https://github.com/matrixji/python-milvus-server',
      packages=['milvus_server'],
      license='Apache-2.0',
      cmdclass={
          'build': CustomBuild,
      },
      package_dir={
          'milvus_server': 'milvus_server'
      },
      package_data={
          'milvus_server': ['data/bin/*', 'data/*.template'],
      },
      options={
          'bdist_wheel': {'plat_name': guess_plat_name()}
      },
      install_requires=[],
      setup_requires=['wheel'],
      entry_points={
          'console_scripts': [
              'milvus-server=milvus_server:main'
          ]
      }
      )
