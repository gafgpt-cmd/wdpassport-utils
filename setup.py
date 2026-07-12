
from setuptools import setup

setup(name='wdpassport_utils',
      version='0.2',
      description='WD My Passport Drive Hardware Encryption Utility for Linux',
      long_description=open('README.md', encoding='utf-8').read(),
      long_description_content_type='text/markdown',
      url='https://github.com/0-duke/wdpassport-utils',
      author='0-duke, crypto-universe, JoshData',
      license='GPLv2',
      python_requires='>=3.8',
      install_requires=[
        'pyudev',
        'py3_sg @ git+https://github.com/crypto-universe/py_sg',
      ],
      scripts=['wdpassport-utils.py'],
      )
