import http.client
import json, time
from bs4 import BeautifulSoup

# Web / Parsing Code
def parseJson(jsonStr):
    try:
        return json.loads(jsonStr);
    except:
        return json.loads("{error:1}");

def scanApts(search, keyword, page=None):
    # Sleep 1/4 second to avoid over-requesting
    time.sleep(0.25);

    # Scan apartments.com listings
    conn = http.client.HTTPSConnection("www.apartments.com")
    payload = json.dumps({
       "Map": {
        "BoundingBox": {
          "LowerRight": {
            "Latitude": 42.33751,
            "Longitude": -71.05413
          },
          "UpperLeft": {
            "Latitude": 42.36808,
            "Longitude": -71.11593
          }
        }
      },
      "Geography": {
        "GeographyType": 7,
        "Location": {
          "Latitude": 42.351,
          "Longitude": -71.094
        }
      },
      "Listing": {
        "MinRentAmount": search["minPrice"],
        "MaxRentAmount": search["maxPrice"],
        "MinBeds": search["minBeds"],
        "MaxBeds": search["minBeds"]+2,
        "Keywords": keyword
      },
      "Paging": {
        "Page": page
      },
      "ResultSeed": 910660,
      "Options": 1
    })
    headers = {
      'accept': 'application/json, text/javascript, */*; q=0.01',
      'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
      'content-type': 'application/json',
      'origin': 'https://www.apartments.com',
    }
    conn.request("POST", "/services/search/", payload, headers)
    res = conn.getresponse()
    data = res.read()
    return(parseJson(data.decode("utf-8")))


def getListingsHtml(jsonObj):
    # {"PlacardState": { "HTML": "<html>"}}
    return jsonObj["PlacardState"]["HTML"]

def getHasMorePages(listingsJson):
    # {"MetaState" : {"PageNextUrl": "https://www.link.com/page"}}
    try:
        return len(listingsJson["MetaState"]["PageNextUrl"]) > 0
    except:
        return False

# Beautiful Soup functions
def getItemByAttr(bsObj, tagName):
    try:
        item = bsObj.find_all('div', attrs={tagName : True})[0][tagName]
    except:
        item = "Error: " + tagName + " not found."
    return item

def getItemByClass(bsObj, tagName, clsName, fieldOfInterest=""):
    try:
        item = bsObj.find_all(tagName, {"class" : clsName})[0]
        if len(fieldOfInterest) > 0:
            return item[fieldOfInterest]
        else:
            return item.encode_contents().decode("utf-8")
    except:
        # print(str(bsObj))
        item = clsName + " not found."
    return item

def parseListing(bsObj, keyword):
    # Parse HTML into JSON data using bs4
    lst = {}
    
    # Address: <div class="property-title" title="16 Greenwich St, Boston, MA">
    lst["address"] = getItemByClass(bsObj, "div", "property-title", "title")
    
    # Zip: <div class="property-address js-url" title="Boston, MA 02120">
    lst["zip"] = getItemByClass(bsObj, "div", "property-address", "title")

    # Keyword from search
    lst["keyword"] = keyword
    
    # Available: <div class="availability">  Avail Sep 01  </div>
    lst["availability"] = getItemByClass(bsObj, "div", "availability")
    
    # Beds: <div class="bed-range"> 4 Bed </div>
    lst["beds"] = getItemByClass(bsObj, "div", "bed-range")

    # Price: <div class="price-range"> $4,800 </div>
    lst["price"] = getItemByClass(bsObj, "div", "price-range")
    
    # Image: <div class="item active" data-image="img.jpg">
    lst["image"] = getItemByAttr(bsObj, 'data-image')
    
    # Phone: <div class="phone-wrapper"> </div>
    lst["phone"] = getItemByClass(bsObj, "a", "phone-link", "href")

    # Link: <a class="property-link" href="https://link.com">
    lst["link"] = getItemByClass(bsObj, "a", "property-link", "href")
    
    # Add timestamp, used for "First seen on: XXXX" text
    lst["time"] = time.time()

    return lst;

def parseListings(bsObj, keyword):
    ulObj = bsObj.find('ul')
    liObjs = ulObj.find_all("li")
    listings = [];
    for liObj in liObjs:
        listingJson = parseListing(liObj, keyword);
        listings.append(listingJson);
    return json.loads(json.dumps(listings))

# Utility Functions
def listingToUniqueId(listing):
    return listing["address"] + listing["price"] + listing["availability"]

def getUniqueListings(listings):
    # Filter redundant listings using up-scope set and predicate.
    uniqueIDs = set();
    def uniquePredicate(listing):
        # Make a Listing->UniqueID function and use it to filter
        listingId = listingToUniqueId(listing);
        if listingId in uniqueIDs:
            return False;
        uniqueIDs.add(listingId)
        return True;
    return list(filter(uniquePredicate, listings))

# Debugging Code - Pretty Printers
def prettyHtml(htmlStr):
    bsObj = BeautifulSoup(htmlStr, "html.parser")
    return bsObj.prettify()

# Apartment Scan Functions
def getListingsForKeyword(search, keyword):
    hasMore = True
    page = 1
    listings = [];
    while hasMore:
        print("Looking up", keyword, "page", page)
        listingsJson = scanApts(search, keyword, page)
        page+=1
        hasMore = getHasMorePages(listingsJson)
        htmlStr = getListingsHtml(listingsJson);
        bsObj = BeautifulSoup(htmlStr, "html.parser")
        listingsJson = parseListings(bsObj, keyword)
        listings.extend(listingsJson)
    print("Found",len(listingsJson),"for keyword",keyword)
    return listings;

def getListingsForKeywords(search):
    listings = [];
    for keyword in search["keywords"]:
        listings.extend(getListingsForKeyword(search, keyword))
    print("Found",len(listings),"for keywords:",", ".join(search["keywords"]))
    unique = getUniqueListings(listings);
    print("Unique listings:",len(unique),"("+str(len(listings)-len(unique))+" duplicates)")
    return unique

def getMetadataForListings(search, listings, newListings):
    # Return stats object used by html template
    return  { 
                "search" : search,
                "numListings" : len(listings),
                "numNewListings" : len(newListings),
            };

# File IO Code
import os
def getFileName():
    # File name ends with hour, meaning only 1 cache file per hour
    folder = "data"
    timestamp = time.time()
    datetime = time.strftime('%Y_%m_%d_%H', time.localtime(timestamp))
    file = "cache_" + datetime + ".json"
    path = os.path.join(os.getcwd(), folder, file)
    return path;

def saveListings(listingsJson):
    fname = getFileName()
    print(fname);
    with open(fname, 'w') as outfile:
        json.dump(listingsJson, outfile, indent=4)

def readJsonFromFile(path, file):
    fname = os.path.join(path, file)
    data = {}
    with open(fname, 'r') as jsonFile:
        data = json.load(jsonFile)
    return data;

def loadRecentListings():
    folder = "data"
    path = os.path.join(os.getcwd(), folder)
    files = os.listdir(path)
    files.sort() # ensure highest alphabetical file is list
    if len(files) == 0:
        return []
    cacheFile = files[-1]
    print("Using", cacheFile, "as cache file.")
    return readJsonFromFile(path, cacheFile)

# Cache Management Functions
def filterListingsInCache(cache, listings):
    # Pre-Condition: All listings in `listings` variable are unique
    # 1. Iterate over new listings
    # 2. Replace new listing with cache value if exists
    # 3. Update cache with all new listings
    cacheIdsList = list(map(listingToUniqueId, cache));
    cacheIdsSet = set(cacheIdsList)
    updatedListings = [];
    newListings = [];
    for listing in listings: # 1. Iterate
        uniqueId = listingToUniqueId(listing)
        if uniqueId in cacheIdsSet: # 2. Cached listings
            idx = cacheIdsList.index(uniqueId)
            updatedListings.append(cache[idx])
        else: # New listing
            newListings.append(listing)
            updatedListings.append(listing)
    cache.extend(newListings) #3 Update cache
    return (updatedListings, newListings, cache)

# Template rendering functions
from flask import render_template
def renderListingHtml(listings, metadata, width):
    path = "listings.html"
    metadata['width'] = width;
    return render_template(path, listings=listings, metadata=metadata)

# Email Updates
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
def emailListings(email, listings, metadata):
    # Set email body to JSON

    # Check environment variables for credentials
    # Probably not safe, but I'm using a throwaway email addr.
    mail_user = os.getenv('EMAIL_USER')
    mail_password = os.getenv('EMAIL_PASS')
    if len(mail_user) == 0 or len(mail_password) == 0:
        print("No email credentials. Skipping update email.")
        return

    # Setup email headers
    # Create message container - the correct MIME type is multipart/alternative.
    beds = metadata["search"]["minBeds"]
    msg = MIMEMultipart('alternative')
    msg['Subject'] = "New Apartment Listings - %d beds [v2]" % beds
    msg['From'] = mail_user
    msg['To'] = email

    # Create the body of the message (a plain-text and an HTML version).
    text = json.dumps(listings, indent=2)
    html = renderListingHtml(listings, metadata, 75)

    # Record the MIME types of both parts - text/plain and text/html.
    part1 = MIMEText(text, 'plain')
    part2 = MIMEText(html, 'html')
    msg.attach(part1)
    msg.attach(part2)

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.ehlo()
        server.login(mail_user, mail_password)
        server.sendmail(msg["From"], msg["To"], msg.as_string())
        server.close()
        print('Email sent to %s!' % msg["To"])
    except  Exception as e:
        print('Something went wrong...')
        print(e)

# Flask App Code
from flask import Flask
import html, json
app = Flask(__name__)

@app.template_filter('joinComma')
def joinComma(lst):
    # timestamp -> Jul 1, 2021 at 12:00pm 
    return ", ".join(lst);

@app.template_filter('timestamp')
def convertToTimestamp(timestamp):
    # timestamp -> Jul 1, 2021 at 12:00pm 
    return time.strftime('%b %d, %Y at %I:%M%p', time.localtime(timestamp))

@app.template_filter('zipCode')
def parseZipCode(zipText):
    # Boston, MA 02120 -> 02120 - Mission Hill 
    zipCode = zipText.split(' ')[-1]
    zips = {
        "02120" : "Mission Hill",
        "02116" : "Back Bay / Bay Village",
        "02445" : "Brookline",
        "02446" : "North Brookline / Coolidge",
        "02115" : "Symphony / Back Bay / Longwood Medical",
        "02118" : "South End / Shumwut / South of Washington",
        "02215" : "Fenway / Kenmore / Longwood Medical",
        "02139" : "Cambridgeport",
        "02113" : "North End",
        "02109" : "North End",
        "02180" : "Beacon Hill / Government Center",
        "02114" : "West End / Beacon Hill",
    };
    return zipCode + " - " + zips.get(zipCode, zipText)

def searchAndRender(search):
    uniqueListings = getListingsForKeywords(search)
    print("Found", len(uniqueListings), "listings.")

    # Compare with most recent lookups
    cache = loadRecentListings();
    cacheSize = len(cache)
    print("Cache size", cacheSize)
    (updatedListings, newListings, updatedCache) = filterListingsInCache(cache, uniqueListings);

    # Make search metadata
    metadata = getMetadataForListings(search, updatedListings, newListings)

    # Sort updateListings by timestamp
    updatedListings.sort(key=lambda x: x["time"], reverse=True)
    newListings.sort(key=lambda x: x["time"], reverse=True)

    # Save updated cache if new listings
    print("New Listings:", len(newListings))
    print("Updated cache size", len(updatedCache))

    assert (len(updatedCache)-cacheSize) == len(newListings)
    if len(updatedCache) != cacheSize:
        saveListings(updatedCache)
    else:
        print("No new listings found. Skipping cache save.")

    # Email new listings, if any
    if len(newListings) > 0:
        saveListings(updatedCache)
        emails = os.getenv('EMAIL_TO').split(" ")
        for email in emails:
            emailListings(email, newListings, metadata)
    else:
        print("No new listings found. Skipping cache save.")

    #return  "<pre>" + html.escape(prettyHtml(updatedListings[0]["html"])) + "</pre>"
    #return "<pre>" + html.escape(json.dumps(updatedListings, indent=2)) + "</pre>"
    return renderListingHtml(updatedListings, metadata, 50)

@app.route('/')
def hello_world():
    # Search listings by keywords
    keywords = ["patio", "deck", "roof", "porch", "private", "pool", "yard"]
    # keywords = ["patio", "deck"]
    minPrice = 4000
    maxPrice = 6400
    minBeds = 4
    search = {
        "keywords" : keywords,
        "minPrice" : minPrice,
        "maxPrice" : maxPrice,
        "minBeds" : minBeds,
    };
    return searchAndRender(search);

@app.route('/3bed')
def find_3beds():
    # Search listings by keywords
    keywords = ["patio", "deck", "roof", "porch", "private", "pool", "yard"]
    # keywords = ["patio", "deck"]
    minPrice = 2500
    maxPrice = 5300
    minBeds = 3
    search = {
        "keywords" : keywords,
        "minPrice" : minPrice,
        "maxPrice" : maxPrice,
        "minBeds" : minBeds,
    };
    return searchAndRender(search);
