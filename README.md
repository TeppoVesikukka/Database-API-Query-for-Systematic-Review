## MongoDB Setup

Some instruction son how to get the mongodb set up for your process:

We will use docker, to allow skipping as many bits of configuration and keep the installation separate from the OS, so it doesn't interfere with other things. 
For clearer setup, we will use a docker compose file, since it allows putting all configuration options in one place.

### The docker compose file
Here is the file, we will use, write it to docker-compose.yml:

```
version: "3"

services: 
  mongo:
    image: mongo:7.0.4
    environment:
      - MONGO_INITDB_ROOT_USERNAME=${MONGOUSER}
      - MONGO_INITDB_ROOT_PASSWORD=${MONGOPASSWORD}
    volumes:
      - ./mongodb:/data
      - ./mongo_dumps:/dumps
    ports:
      - 127.0.0.1:27017:27017
```
Explanations: 
 - `services` lists all services we want to run.
 - `environment` : List all environment variables. For mongo the `MONGO_INITDB_ROOT_USERNAME` and `MONGO_INITDB_ROOT_PASSWORD`
   variables set the user name and password respectively. `${MONGOUSER}` would indicate that this should be retrieved from an environment variable MONGOUSER, but you can also replace them by values.
 - `volumes`: volumes specify files/folders that are mapped from your host system to the file system in docker. they are defined as <hostPath>:<containerPath> i.e. <hostPath> on the host is mapped to <containerPath> in the container.
   In the mongodb container /data contains all the relevant data for the database. NOTE: This will be owned by root (which is running docker) and not by your user.   
   Also, make sre to add the host path to the `.gitignore` file so you don't accidentially push it to github.
   We also put a dumps folder in there to allow dumping (i.e. exporting) the database more easily.
 - `ports`: Indicates ports that should be mapped to the host. Format is <host>:<hostPort>:<containerPort>. host is optional, but if you e.g. want to make the port available to requests from outide you would have to bind it to 0.0.0.0.
   The 127.0.0.1 indicates it is a local callback, so only available from your machine. 27017 is the standard port and shouldn't be changed as most clients assume to find the database on that port by default. 

### Run the database

Go to the folder and run `docker compose up` (if you have named the file other than `docker-compose.yml` you will have to run `docker compose -f <filename> up`.
Now you have the database up and running. 

### Export the database
Simply run the mongodump command in the database container:

`docker exec -it mongo mongodump --out /dumps`

The data will now be in `./mongo_dumps` NOTE: The data will be owned by root, so you will need to copy this to some other place as root.
If the above command fails, check `docker container ls` for the name of the mongo container. You might need to replace the <mongo> by that name. 

### Import an existing database
Copy the dump to `./mongo_dumps`

`docker exec -it mongo mongorestore /dumps`
This will load all elements of the db into the db run in the container.

If you want to clean everything before run:
`docker exec -it mongo mongorestore --drop /dumps`





   
