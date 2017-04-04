# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure(2) do |config|
  # The most common configuration options are documented and commented below.
  # For a complete reference, please see the online documentation at
  # https://docs.vagrantup.com.

  # Every Vagrant development environment requires a box. You can search for
  # boxes at https://atlas.hashicorp.com/search.
  config.vm.box = "ubuntu/trusty64"

  config.vm.synced_folder ".", "/vagrant"

  # Speed up DNS lookups
  config.vm.provider "virtualbox" do |vb|
    vb.customize ["modifyvm", :id, "--natdnsproxy1", "off"]
    vb.customize ["modifyvm", :id, "--natdnshostresolver1", "off"]
  end

  # Django dev server
  config.vm.network "forwarded_port", guest: 8000, host: 8000

  # Give the VM a bit more power to speed things up
  config.vm.provider "virtualbox" do |v|
    v.memory = 2048
    v.cpus = 2
  end

  config.vm.provision "shell", inline: <<-SHELL
    cd /vagrant

    # Install the packages from conf/packages.ubuntu-trusty
    apt-get update
    xargs sudo apt-get install -qq -y < conf/packages.ubuntu-trusty
    # Install some of the other things we need that are just for dev
    # git for installing mapit from the repo directly
    sudo apt-get install -qq -y git

    sudo -u postgres psql -c "CREATE USER mapit SUPERUSER CREATEDB PASSWORD 'mapit'"
    sudo -u postgres psql -c "CREATE DATABASE mapit"
    sudo -u postgres psql -c "CREATE EXTENSION postgis; CREATE EXTENSION postgis_topology;" -d mapit

    # Copy the example config file into place to get things going
    cp conf/general.yml-example conf/general.yml

    # Run post-deploy actions script to create a virtualenv, install the
    # python packages we need, migrate the db and generate the sass etc
    conf/pre_deploy_actions.bash
    conf/post_deploy_actions.bash
  SHELL
end
