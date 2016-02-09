sudo apt-get update
sudo apt-get install -y python-pip

sudo easy_install jinja2
sudo easy_install azure

mkdir manifests

for f in bosh.yml manifests/index.yml setup_dns.py create_cert.sh setup_devbox.py deploy_bosh_and_releases.py init.sh 98-msft-love-cf
do
   curl --silent \
        https://raw.githubusercontent.com/cf-platform-eng/bosh-azure-template/master/$f \
        > $f
done

\cp -R * ../../
cd ../../

# start tmux, running deploy_bosh_and_releases
tmux -S /tmp/shared-tmux-session new -d -s shared 'python setup_devbox.py && python deploy_bosh_and_releases.py'
chmod 777 /tmp/shared-tmux-session
