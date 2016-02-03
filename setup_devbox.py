#!/usr/bin/env python
import os
import sys
import re
import json
import urllib
import base64
import traceback
import yaml

from jinja2 import Template
from subprocess import call
from Utils.WAAgentUtil import waagent
import Utils.HandlerUtil as Util
from azure.storage import BlobService
from azure.storage import TableService

call("mkdir -p ./bosh", shell=True)
call("mkdir -p ./bosh/manifests", shell=True)

# Get settings from CustomScriptForLinux extension configurations
waagent.LoggerInit('/var/log/waagent.log', '/dev/stdout')
hutil =  Util.HandlerUtility(waagent.Log, waagent.Error, "bosh-deploy-script")
hutil.do_parse_context("enable")
settings = hutil.get_public_settings()
with open (os.path.join('bosh','settings'), "w") as tmpfile:
    tmpfile.write(json.dumps(settings, indent=4, sort_keys=True))
username = settings["username"]
home_dir = os.path.join("/home", username)
install_log = os.path.join(home_dir, "install.log")

# Prepare the containers
storage_account_name = settings["STORAGE-ACCOUNT-NAME"]
storage_access_key = settings["STORAGE-ACCESS-KEY"]
blob_service = BlobService(storage_account_name, storage_access_key)
blob_service.create_container('bosh')
blob_service.create_container(container_name='stemcell',
    x_ms_blob_public_access='blob'
)

# Prepare the table for storing meta datas of storage account and stemcells
table_service = TableService(storage_account_name, storage_access_key)
table_service.create_table('stemcells')

# Generate the private key and certificate
call("sh create_cert.sh", shell=True)
call("cp bosh.key ./bosh/bosh", shell=True)
with open ('bosh_cert.pem', 'r') as tmpfile:
    ssh_cert = tmpfile.read()
ssh_cert = "|\n" + ssh_cert
ssh_cert="\n        ".join([line for line in ssh_cert.split('\n')])

settings['SSH_CERTIFICATE'] = ssh_cert

f = open('manifests/index.yml')
manifests = yaml.safe_load(f)
f.close()

m_list = []
for m in manifests['manifests']:
    m_list.append("manifests/{0}".format(m['file']))

m_list.append('bosh.yml')

# Get github path
github_path = "https://raw.githubusercontent.com/cf-platform-eng/bosh-azure-template/master"

norm_settings = {}
norm_settings["DIRECTOR_UUID"] = "{{ DIRECTOR_UUID }}"

for setting in settings:
    norm_settings[setting.replace("-", "_")] = settings[setting]

# Render the yml template for bosh-init
for template_path in m_list:

    # Download the manifest if it doesn't exits
    if not os.path.exists(template_path):
        urllib.urlretrieve("{0}/{1}".format(github_path, template_path), template_path)

    if os.path.exists(template_path):
        with open (template_path, 'r') as f:
            contents = f.read()
            template = Template(contents)
            contents = template.render(norm_settings)

    with open (os.path.join('bosh', template_path), 'w') as f:
        f.write(contents)

# Copy all the files in ./bosh into the home directory
call("cp -r ./bosh/* {0}".format(home_dir), shell=True)
call("cp ./manifests/index.yml {0}/manifests/".format(home_dir), shell=True)

call("chown -R {0} {1}".format(username, home_dir), shell=True)
call("chmod 400 {0}/bosh".format(home_dir), shell=True)

#Install bosh_cli and bosh-init
call("mkdir /mnt/bosh_install; cp init.sh /mnt/bosh_install; cd /mnt/bosh_install; sh init.sh >{0} 2>&1;".format(install_log), shell=True)

# Setup the devbox as a DNS
enable_dns = settings["enable-dns"]
if enable_dns:
    try:
        import urllib2
        cf_ip = settings["cf-ip"]
        dns_ip = re.search('\d+\.\d+\.\d+\.\d+', urllib2.urlopen("http://www.whereismyip.com").read()).group(0)
        call("python setup_dns.py -d cf.azurelovecf.com -i 10.0.16.4 -e {0} -n {1} >/dev/null 2>&1".format(cf_ip, dns_ip), shell=True)
        # Update motd
        call("cp -f 98-msft-love-cf /etc/update-motd.d/", shell=True)
        call("chmod 755 /etc/update-motd.d/98-msft-love-cf", shell=True)
    except Exception as e:
        err_msg = "\nWarning:\n"
        err_msg += "\nFailed to setup DNS with error: {0}, {1}".format(e, traceback.format_exc())
        err_msg += "\nYou can setup DNS manually with \"python setup_dns.py -d cf.azurelovecf.com -i 10.0.16.4 -e External_IP_of_CloudFoundry -n External_IP_of_Devbox\""
        err_msg += "\nExternal_IP_of_CloudFoundry can be found in {0}/settings.".format(home_dir)
        err_msg += "\nExternal_IP_of_Devbox is the dynamic IP which can be found in Azure Portal."
        with open(install_log, 'a') as f:
            f.write(err_msg)
