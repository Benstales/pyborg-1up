Deploying pyborg on modern computers
====================================

..note:: Hey this isn't up to date 
         This doesn't work as is for the poetry-managed source in pyborg v2+


docker-compose
--------------
Checkout the Dockerfile(s) in the source. There's also a :kbd:`docker-compose.yml` file to get you started.


Systemd Unit files
------------------

  * Create :program:`pyborg` user (:kbd:`adduser pyborg --no-create-home --shell /bin/false`)

  * Install pyborg with poetry from source (git) or via pypi (also via :kbd:`pip`).

  * Edit the unit files to match your system. (you probably aren't named Jack.)

  * install these unit files into your systemd path. (try :kbd:`/usr/lib/systemd/system`)

  * reload your systemd (:kbd:`systemctl daemon-reload`)

  * Raise the services. (:kbd:`systemctl start pyborg_http` & :kbd:`systemctl start pyborg_discord`)


..  highlight:: cfg


pyborg_http.service ::

	[Unit]
	Description=Pyborg multiplexing server
	After=network.target

	[Service]
	WorkingDirectory=/home/jack/src/pyborg-1up/pyborg
	ExecStart=/usr/local/bin/pipenv run pyborg http
	ExecReload=/bin/kill -HUP $MAINPID
	KillMode=process
	Restart=on-failure
	User=pyborg

	[Install]
	WantedBy=multi-user.target

..


pyborg_discord.service ::

	[Unit]
	Description=Pyborg Discord Client
	After=network.target
	Requires=pyborg_http.service

	[Service]
	WorkingDirectory=/home/jack/src/pyborg-1up/pyborg
	ExecStart=/usr/local/bin/pipenv run pyborg discord
	ExecReload=/bin/kill -HUP $MAINPID
	KillMode=process
	Restart=on-failure
	User=pyborg

	[Install]
	WantedBy=multi-user.target

..

pyborg_http_saver.service ::

	[Unit]
	Description=Pyborg HTTP Saver
	After=network.target
	#Requires=pyborg_http.service

	[Service]
	WorkingDirectory=/home/jack/src/pyborg-1up/pyborg
	# this uses httpie
	ExecStart=/usr/bin/http post :2001/save
	User=pyborg

..



pyborg_http_saver.timer ::
	
	[Unit]
	Description=Save and backup pyborg brain

	[Timer]
	OnBootSec=15min
	OnUnitActiveSec=30min 

	[Install]
	WantedBy=timers.target

..



pyborg_http_stats.service ::

	[Unit]
	Description=Pyborg Stats Saver
	After=network.target
	#Requires=pyborg_http.service

	[Service]
	WorkingDirectory=/home/jack/src/pyborg-1up/pyborg
	ExecStart=/usr/bin/http post :2001/stats
	User=pyborg
	
..


pyborg_http_stats.timer ::
	
	[Unit]
	Description=Save stats snapshot of pyborg

	[Timer]
	OnUnitActiveSec=30min

	[Install]
	WantedBy=timers.target

..