
from setuptools import setup

setup(name='wdpassport_utils',
      version='0.3.0',
      description='WD My Passport Drive Hardware Encryption Utility for Linux',
      long_description=open('README.md', encoding='utf-8').read(),
      long_description_content_type='text/markdown',
      url='https://github.com/0-duke/wdpassport-utils',
      author='0-duke, crypto-universe, JoshData',
      license='GPLv2',
      python_requires='>=3.8',
      install_requires=[
        'pyudev',
        'typer>=0.12',
        # main() catches click.Abort/ClickException directly. Typer used to
        # pull click in transitively, but stopped doing so (>=0.27), which
        # made the CLI crash on ModuleNotFoundError. Declare it explicitly.
        'click',
      ],
      packages=['wdpassport'],
      entry_points={
        'console_scripts': [
          'wdpassport=wdpassport.cli:main',
          'wdpassport-gui=wdpassport.gui:main',
          'wd-tray=wdpassport.tray:main',
        ],
      },
      )
