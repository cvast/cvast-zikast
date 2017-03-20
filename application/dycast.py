#$Id: dycast.py,v 1.15 2008/04/08 15:56:03 alan Exp alan $
# DYCAST functions

import sys
import os
import shutil
import datetime
import time
import fileinput
import ConfigParser
import logging
from ftplib import FTP

if sys.platform == 'win32':
    lib_dir = "C:\\DYCAST\\application\\libs"
else:
    lib_dir = "/Users/alan/Documents/DYCAST/py_bin/libs"

sys.path.append(lib_dir)            # the hard-coded library above
sys.path.append("libs")             # a library relative to current folder

sys.path.append(lib_dir+os.sep+"dbfpy") # the hard-coded library above
sys.path.append("libs"+os.sep+"dbfpy")  # a library relative to current folder

try:
    import dbf
except ImportError:
    print "couldn't import dbf library in path:", sys.path
    sys.exit()

sys.path.append(lib_dir+os.sep+"psycopg2")  # the hard-coded library above
sys.path.append("libs"+os.sep+"psycopg2")   # a library relative to current folder

try:
    import psycopg2
except ImportError:
    print "couldn't import psycopg2 library in path:", sys.path
    sys.exit()

#loglevel = logging.DEBUG        # For debugging
loglevel = logging.INFO         # appropriate for normal use
#loglevel = logging.WARNING      # appropriate for almost silent use

conn = 0
cur = 0
dbfn = 0
riskdate_tuple = ()

# Conversions and the DYCAST parameters:
miles_to_metres = 1609.34722
#TODO: find a more appropriate way to initialize these
sd = 1
cs = 1
ct = 1
td = 1
threshold = 1

# postgresql database connection information and table names
dsn = "x"
dead_birds_table_unprojected = "x"
dead_birds_table_projected = "x"
effects_poly_table = "x"

# dist_margs means "distribution marginals" and is the result of the
# monte carlo simulations.  See Theophilides et al. for more information
#def create_dist_margs():
#def create_analysis_grid():
#def load_prepared_dist_margs():
#def load_prepared_analysis_grid():
#def post_analysis_functions():
#def kappa_test():

def read_config(filename):
    # All dycast objects must be initialized from a config file, therefore,
    # all dycast applications must include the name of a config file, or they
    # must use the default, which is dycast.config in the current directory

    global dbname
    global user
    global password
    global host
    global dsn
    global ftp_site
    global ftp_user
    global ftp_pass
    global dead_birds_filename
    global dead_birds_dir
    global risk_file_dir
    global lib_dir
    global dead_birds_table_unprojected
    global dead_birds_table_projected
    global effects_poly_table
    global sd
    global td
    global cs
    global ct
    global threshold
    global logfile

    config = ConfigParser.SafeConfigParser()
    config.read(filename)

    dbname = config.get("database", "dbname")
    user = config.get("database", "user")
    password = config.get("database", "password")
    host = config.get("database", "host")
    dsn = "dbname='" + dbname + "' user='" + user + "' password='" + password + "' host='" + host + "'"

    ftp_site = config.get("ftp", "server")
    ftp_user = config.get("ftp", "username")
    ftp_pass = config.get("ftp", "password")
    dead_birds_filename = config.get("ftp", "filename")
    if sys.platform == 'win32':
        logfile = config.get("system", "windows_dycast_path") + config.get("system", "logfile")
        dead_birds_dir = config.get("system", "windows_dycast_path") + config.get("system", "dead_birds_subdir")
        risk_file_dir = config.get("system", "windows_dycast_path") + config.get("system", "risk_file_subdir")
    else:
        logfile = config.get("system", "unix_dycast_path") + config.get("system", "logfile")
        dead_birds_dir = config.get("system", "unix_dycast_path") + config.get("system", "dead_birds_subdir")
        risk_file_dir = config.get("system", "unix_dycast_path") + config.get("system", "risk_file_subdir")

    dead_birds_table_unprojected = config.get("database", "dead_birds_table_unprojected")
    dead_birds_table_projected = config.get("database", "dead_birds_table_projected")
    effects_poly_table = config.get("database", "effects_poly_table")

    sd = float(config.get("dycast", "spatial_domain")) * miles_to_metres
    cs = float(config.get("dycast", "close_in_space")) * miles_to_metres
    ct = int(config.get("dycast", "close_in_time"))
    td = int(config.get("dycast", "temporal_domain"))
    threshold = int(config.get("dycast", "bird_threshold"))

def init_logging():
    logging.basicConfig(format='%(asctime)s %(levelname)8s %(message)s', 
        filename=logfile, filemode='a')
    logging.getLogger().setLevel(loglevel)

def debug(message):
    logging.debug(message)

def info(message):
    logging.info(message)

def warning(message):
    logging.warning(message)

def error(message):
    logging.error(message)

def create_db(dbname):
    # Currently this doesn't work
    try:
        #conn = psycopg2.connect("dbname='template1' user='" + user + "' host='" + host + "'")
        conn = psycopg2.connect("user='" + user + "' host='" + host + "'")
    except Exception, inst:
        logging.error("Unable to connect to server")
        logging.error(inst)
        sys.exit()
    #conn.autocommit(True)
    #conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    #conn.switch_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    try:
        cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
    except Exception, inst:
        logging.error(inst)
        return 0

    try:
        cur.execute("CREATE DATABASE " + dbname)
    except Exception, inst:
        logging.error(inst)
        return 0

    return 1
    

def init_db():
    global cur, conn
    try:
        conn = psycopg2.connect(dsn)
    except Exception, inst:
        logging.error("Unable to connect to database")
        logging.error(inst)
        sys.exit()
    cur = conn.cursor()

##########################################################################
##### functions for loading data:
##########################################################################

def load_bird(line):
    try:
        (bird_id, report_date_string, lon, lat, species) = line.split("\t")
    except ValueError:
        logging.warning("SKIP incorrect number of fields: %s", line.rstrip())
        return 0
    # We need to force this query to take lon and lat as the strings 
    # that they are, not quoted as would happen if I tried to list them 
    # in the execute statement.  That's why they're included in this line.
    querystring = "INSERT INTO " + dead_birds_table_projected + " VALUES (%s, %s, %s, ST_Transform(GeometryFromText('POINT(" + lon + " " + lat + ")',4269),54003))"
    #querystring = "INSERT INTO " + dead_birds_table_unprojected + " VALUES (%s, %s, %s, GeometryFromText('POINT(" + lon + " " + lat + ")',4269))"
    try:
        cur.execute(querystring, (bird_id, report_date_string, species))
    except Exception, inst:
        conn.rollback()
        if str(inst).startswith("duplicate key"): 
            logging.debug("couldn't insert duplicate dead bird key %s, skipping...", bird_id)
            return -1
        else:
            logging.warning("couldn't insert dead bird record")
            logging.warning(inst)
            return 0
    conn.commit()
    return bird_id

#def analyze_tables():
    # This must be run outside a transaction block.  However, psycopg2 has 
    # a problem doing that on Mac

    #querystring = "VACUUM ANALYZE " + dead_birds_table_projected
    #try:
    #    cur.execute(querystring)
    #except Exception, inst:
    #    print inst

##########################################################################
##### functions for exporting results:
##########################################################################

def export_risk(riskdate, format = "dbf", path = None):
    if path == None:
        path = risk_file_dir + "/tmp/"
        using_tmp = True
    else:
        using_tmp = False


    # riskdate is a date object, not a string
    try:
        riskdate_string = riskdate.strftime("%Y-%m-%d")
    except:
        logging.error("couldn't convert date to string: %s", riskdate)
        return 0
    querystring = "SELECT tile_id, num_birds, close_pairs, close_space, close_time, nmcm FROM \"risk%s\"" % riskdate_string
    try:
        cur.execute(querystring) 
    except Exception, inst:
        conn.rollback()
        logging.error("couldn't select risk for date: %s", riskdate_string)
        logging.error(inst)
        return 0

    if format == "txt":
        txt_out = init_txt_out(riskdate, path)
    else:   # dbf or other
        dbf_out = init_dbf_out(riskdate, path)

    rows = cur.fetchall()
    
    if format == "txt":
        # Currently just sprints to stdout.  Fix this later if needed
        for row in rows:
            # Be careful of the ordering of space and time in the db vs the txt file
            [id, num_birds, close_pairs, close_space, close_time, nmcm] = row
            print "%s\t1.5\t0.2500\t3\t%s\t%s\t?.???\t%s\t%s\t%s" % (id, num_birds, close_pairs, close_time, close_space, nmcm)
        txt_close()
    else:
        for row in rows:
            # Be careful of the ordering of space and time in the db vs the txt file
            [id, num_birds, close_pairs, close_space, close_time, nmcm] = row
            dbf_print(id, nmcm)
        dbf_close()
        if using_tmp:
            dir, base = os.path.split(dbf_out.name)
            dir, tmp = os.path.split(dir)   # Remove the "tmp" to get outbox
            outbox_tmp_to_new(dir, base)    # Move finished file to "new"
        

def init_txt_out(riskdate, path):
    # Currently just sprints to stdout.  Fix this later if needed
    print "ID\tBuf\tcs\tct\tnum\tpairs\texp\tT_Only\tS_Only\tnmcm"

def init_dbf_out(riskdate, path = None):
    if path == None:
        path = "."
    global dbfn
    global riskdate_tuple
    filename = path + os.sep + "risk" + riskdate.strftime("%Y-%m-%d") + ".dbf"
    dbfn = dbf.Dbf(filename, new=True)
    dbfn.addField(
        ("ID",'N',8,0),
        ("COUNTY",'N',3,0),
        ("RISK",'N',1,0),
        ("DISP_VAL",'N',8,6),
        ("DATE",'D',8)
    )

    riskdate_tuple = (int(riskdate.strftime("%Y")), int(riskdate.strftime("%m")), int(riskdate.strftime("%d")))

    #TODO: make this an object
    return dbfn

def txt_print(id, num_birds, close_pairs, close_space, close_time, nmcm):
    print "%s\t1.5\t0.2500\t3\t%s\t%s\t?.???\t%s\t%s\t%s" % (id, num_birds, close_pairs, close_time, close_space, nmcm)
    
def dbf_print(id, nmcm):
    global dbfn
    global riskdate_tuple
    rec = dbfn.newRecord()
    rec['ID'] = id
    rec['COUNTY'] = get_county_id(id)
    if nmcm > 0:
        rec['RISK'] = 1
    else:
        rec['RISK'] = 0
    rec['DISP_VAL'] = nmcm 
    rec['DATE'] = riskdate_tuple  
    rec.store()
   
def txt_close():
    # Currently just sprints to stdout.  Fix this later if needed
    print "done" 

def dbf_close():
    global dbfn
    dbfn.close()

##########################################################################
##### functions for uploading and downloading files:
##########################################################################

# The outbox functions are based on the Maildir directory structure.
# The use of /tmp/ allows to spend a lot of time writing to the file, 
# if necessary, and then atomically move it to a /new/ directory, where
# other scripts can find it.  In this way, the /new/ directory will never
# include incomplete files that are still being written.

def outbox_tmp_to_new(outboxpath, filename):
    shutil.move(outboxpath + "/tmp/" + filename, outboxpath + "/new/" + filename)
    
def outbox_new_to_cur(outboxpath, filename):
    shutil.move(outboxpath + "/new/" + filename, outboxpath + "/cur/" + filename)

def backup_birds():
    (stripped_file, ext) = os.path.splitext(dead_birds_filename)
    #stripped_file = dead_birds_filename.rstrip("tsv")
    #stripped_file = stripped_file.rstrip("txt")    # Just in case
    new_file = stripped_file + "_" + datetime.date.today().strftime("%Y-%m-%d") + ".tsv"
    shutil.copyfile(dead_birds_dir + dead_birds_filename, dead_birds_dir + new_file)

def download_birds():
    localfile = open(dead_birds_dir + os.sep + dead_birds_filename, 'w')

    try:
        ftp = FTP(ftp_site, ftp_user, ftp_pass)
    except Exception, inst:
        logging.error("could not download birds: unable to connect")
        logging.error(inst)
        localfile.close()
        sys.exit()
       
    try: 
        ftp.retrbinary('RETR ' + dead_birds_filename, localfile.write)
    except Exception, inst:
        logging.error("could not download birds: unable retrieve file")
        logging.error(inst)
        #sys.exit() # If there's no birds, we should still generate risk
    localfile.close()

def load_bird_file(filename = None):
    if filename == None:
        filename = dead_birds_dir + os.sep + dead_birds_filename
    lines_read = 0
    lines_processed = 0
    lines_loaded = 0
    lines_skipped = 0
    for line in fileinput.input(filename):
        if fileinput.filelineno() != 1:
            lines_read += 1
            result = 0
            result = load_bird(line)

            # If result is a bird ID or -1 (meaning duplicate) then:
            if result:                  
                lines_processed += 1
                if result == -1:
                    lines_skipped += 1
                else:
                    lines_loaded += 1

    # dycast.analyze_tables()   
    logging.info("bird load complete: %s processed %s of %s lines, %s loaded, %s duplicate IDs skipped", filename, lines_processed, lines_read, lines_loaded, lines_skipped)
    return lines_read, lines_processed, lines_loaded, lines_skipped
 

def upload_new_risk(outboxpath = None):
    if outboxpath == None:
        outboxpath = risk_file_dir
    newdir = outboxpath + "/new/"
    for file in os.listdir(newdir):
         if ((os.path.splitext(file))[1] == '.dbf'):
            logging.debug("uploading %s and moving it from new/ to cur/", file)
            upload_risk(newdir, file)
            outbox_new_to_cur(outboxpath, file)

def upload_risk(path, filename):
    ######
    ###### Not tested
    ######
    
    # Fix this: allow uploading multiple files:
    # Also check if this should use outboxpath
    localfile = open(path + os.sep + filename)
    
    ftp = FTP(ftp_site, ftp_user, ftp_pass)
    ftp.storbinary('STOR ' + filename, localfile)
    localfile.close()

##########################################################################
##### functions for generating risk:
##########################################################################

def create_temp_bird_table(riskdate, days_prev):
    enddate = riskdate
    startdate = riskdate - datetime.timedelta(days=(days_prev))
    tablename = "dead_birds_" + startdate.strftime("%Y-%m-%d") + "_to_" + enddate.strftime("%Y-%m-%d")
    querystring = "CREATE TEMP TABLE \"" + tablename + "\" AS SELECT * FROM " + dead_birds_table_projected + " where report_date >= %s and report_date <= %s" 
    try:
        cur.execute(querystring, (startdate, enddate))
    except Exception, inst:
        conn.rollback()
        # If string includes "already exists"...
        if str(inst).find("already exists"): 
            cur.execute("DROP TABLE \"" + tablename + "\"")
            cur.execute(querystring, (startdate, enddate))
        else:
            logging.error(inst)
            sys.exit()
    conn.commit()
    return tablename

def create_daily_risk_table(riskdate):
    tablename = "risk" + riskdate.strftime("%Y-%m-%d") 
    querystring = "CREATE TABLE \"" + tablename + "\" (LIKE \"risk_table_parent\" INCLUDING CONSTRAINTS)"
    # the foreign key constraints are not being copied for some reason.
    try:
        cur.execute(querystring)
    except Exception, inst:
        conn.rollback()
        # TODO: save old version of risk instead of overwriting
        try:   
            cur.execute("DROP TABLE \"" + tablename + "\"")
            cur.execute(querystring)
        except:
            conn.rollback()
            logging.error("couldn't create risk table: %s", tablename)
            sys.exit()
    conn.commit()
    return tablename


def get_ids(startpoly=None, endpoly=None):
    try:
        if endpoly != None and startpoly != None:
            querystring = "SELECT tile_id from " + effects_poly_table + " where tile_id >= %s and tile_id <= %s"
            cur.execute(querystring, (startpoly, endpoly))
        elif startpoly != None:
            querystring = "SELECT tile_id from " + effects_poly_table + " where tile_id >= %s"
            cur.execute(querystring, (startpoly,))
        else:
            querystring = "SELECT tile_id from " + effects_poly_table
            cur.execute(querystring)
    except Exception, inst:
        logging.error("can't select tile_id from %s", effects_poly_table)
        logging.error(inst)
        sys.exit()
    rows = cur.fetchall()
    return rows

def get_county_id(tile_id):
    try:
        #TODO: This poly table needs to be the one with counties in it
        # I'm not sure why it works adding the tile_id as a string, but
        # doesn't work if I replace it with %s and include it in 
        #cur.execute as a second argument
        querystring = "SELECT county FROM effects_polys where tile_id = " + str(tile_id)
        cur.execute(querystring)
    except Exception, inst:
        conn.rollback()
        logging.warning("warning: can't select county for effects poly %s", tile_id)
        logging.warning(inst)
        return 0
    return cur.fetchone()[0]


def check_bird_count(bird_tab, tile_id):
    querystring = "SELECT count(*) from \"" + bird_tab + "\" a, " + effects_poly_table + " b where b.tile_id = %s and st_distance(a.location,b.the_geom) < %s" 
    try:
        cur.execute(querystring, (tile_id, sd))
    except Exception, inst:
        conn.rollback()
        logging.error("can't select bird count")
        logging.error(inst)
        sys.exit()
    new_row = cur.fetchone()
    return new_row[0]

def print_bird_list(bird_tab, tile_id):
    querystring = "SELECT bird_id from \"" + bird_tab + "\" a, " + effects_poly_table + " b where b.tile_id = %s and st_distance(a.location,b.the_geom) < %s" 
    try:
        cur.execute(querystring, (tile_id, sd))
    except Exception, inst:
        conn.rollback()
        logging.error("can't select bird list")
        logging.error(inst)
        sys.exit()
    for row in cur.fetchall():
        print row[0]

def create_effects_poly_bird_table(bird_tab, tile_id):
    tablename = "temp_table_bird_selection" 
    #tablename = bird_tab + "_" + tile_id
    # I don't think this can be a temp table, or else I'd have to use "EXECUTE"
    # (See Postgresql FAQ about functions and temp tables)
    querystring = "CREATE TABLE \"" + tablename + "\" AS SELECT * from \"" + bird_tab + "\" a, " + effects_poly_table + " b where b.tile_id = %s and st_distance(a.location,b.the_geom) < %s" 
    try:
        #logging.info("selecting CREATE TABLE with st_distance(a.location,b.the_geom) < %s", sd)
        cur.execute(querystring, (tile_id, sd))
    except:
        conn.rollback()
        cur.execute("DROP TABLE \"" + tablename + "\"")
        cur.execute(querystring, (tile_id, sd))
    conn.commit()
    return tablename 

def cst_cs_ct_wrapper():
    querystring = "SELECT * FROM cst_cs_ct(%s, %s)"
    try:
        #logging.info("selecting SELECT * FROM cst_cs_ct(%s, %s)", cs, ct)
        cur.execute(querystring, (cs, ct))
    except Exception, inst:
        conn.rollback()
        logging.error("can't select cst_cs_ct function")
        logging.error(inst)
        sys.exit()
    return cur.fetchall()
  
def nmcm_wrapper(num_birds, close_pairs, close_space, close_time):
    querystring = "SELECT * FROM nmcm(%s, %s, %s, %s)"
    try:
        cur.execute(querystring, (num_birds, close_pairs, close_space, close_time))
    except Exception, inst:
        conn.rollback()
        logging.error("can't select nmcm function")
        logging.error(inst)
        sys.exit()
    return cur.fetchall()
  
def insert_result(riskdate, tile_id, num_birds, close_pairs, close_time, close_space, nmcm):
    tablename = "risk" + riskdate.strftime("%Y-%m-%d") 
    querystring = "INSERT INTO \"" + tablename + "\" (tile_id, num_birds, close_pairs, close_space, close_time, nmcm) VALUES (%s, %s, %s, %s, %s, %s)"
    try:
        # Be careful of the ordering of space and time in the db vs the txt file
        cur.execute(querystring, (tile_id, num_birds, close_pairs, close_space, close_time, nmcm))
    except Exception, inst:
        conn.rollback()
        logging.error("couldn't insert effects_poly risk")
        logging.error(inst)
        return 0
    conn.commit()
         

def daily_risk(riskdate, startpoly=None, endpoly=None):
    rows = get_ids(startpoly, endpoly)

    risk_tab = create_daily_risk_table(riskdate)
    dead_birds_daterange = create_temp_bird_table(riskdate, td)

    st = time.time()
    if startpoly or endpoly:
        logging.info("Starting daily_risk for %s, startpoly: %s, endpoly: %s", riskdate, startpoly, endpoly)
    else:
        logging.info("Starting daily_risk for %s", riskdate)

    inc = 0
    for row in rows:
        tile_id = row[0]
        inc += 1
        if not inc % 1000:
            logging.debug("tile_id: %s done: %s time elapsed: %s", tile_id, inc, time.time() - st)
        num_birds = check_bird_count(dead_birds_daterange, tile_id)
        if num_birds >= threshold:
            create_effects_poly_bird_table(dead_birds_daterange, tile_id)
            st0 = time.time()
            results = cst_cs_ct_wrapper()
            st1 = time.time()
            close_pairs = results[0][0]
            close_space = results[1][0] - close_pairs
            close_time = results[2][0] - close_pairs
            #print "tile ", tile_id, "found", num_birds, "birds (above threshold) %s actual close pairs, %s close in space, %s close in time" % (close_pairs, close_space, close_time)
            #print_bird_list(dead_birds_daterange, tile_id)
            result2 = nmcm_wrapper(num_birds, close_pairs, close_space, close_time)
            insert_result(riskdate, tile_id, num_birds, close_pairs, close_time, close_space, result2[0][0])
     
    #logging.info("Finished daily_risk for %s: done %s tiles, time elapsed: %s seconds", riskdate, inc, time.time() - st)
    logging.info("Finished daily_risk for %s: done %s tiles", riskdate, inc)

##########################################################################
##########################################################################