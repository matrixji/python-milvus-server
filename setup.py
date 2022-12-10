import pathlib
from os import makedirs, listdir, environ
from os.path import join, abspath, dirname, isfile
from datetime import datetime
import shutil
from distutils.core import setup
from distutils.command.build import build


def get_package_version():
    base_version = '2.2.0'
    if 'MILVUS_SERVER_VERSION' in environ:
        return environ['MILVUS_SERVER_VERSION']
    return f'{base_version}.dev{datetime.now().strftime("%Y%m%d%H%M")}'


def copy_bin_data():
    milvus_server_bin_dir = join(dirname(abspath(__file__)), 'milvus', 'bin')
    dest_bin_dir = join(dirname(abspath(__file__)), 'milvus_server', 'data', 'bin')
    shutil.rmtree(dest_bin_dir, ignore_errors=True)
    makedirs(dest_bin_dir, exist_ok=True)
    for filename in listdir(milvus_server_bin_dir):
        filepath = join(milvus_server_bin_dir, filename)
        ext_name = filepath.rsplit('.')[-1]
        if isfile(filepath) and ext_name in ('exe', 'dll', 'so', 'dylib', filename):
            shutil.copy(filepath, join(dest_bin_dir, filename), follow_symlinks=False)


class CustomBuild(build):
    def run(self):
        copy_bin_data()
        build.run(self)


setup(name='python-milvus-server',
      version=get_package_version(),
      description='Python Milvus Server',
      long_description=(pathlib.Path(__file__).parent / 'README.md').read_text(),
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
          'bdist_wheel': {'plat_name': 'win-amd64'}
      },
      setup_requires=['wheel']
      )
