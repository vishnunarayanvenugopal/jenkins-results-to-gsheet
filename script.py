import json
import urllib
import re
import gspread
import time
import os
import requests
from urllib.request import urlopen
from oauth2client.service_account import ServiceAccountCredentials
from collections import Counter

# define the scope
scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']

# add credentials to the account
creds = ServiceAccountCredentials.from_json_keyfile_name('secret.json', scope)

# authorize the clientsheet
client = gspread.authorize(creds)

def ReturnJSONfromURL(URL):
    try:
        with urllib.request.urlopen(URL+"/api/json") as url:
            data = json.loads(url.read().decode())
        return data
    except:
        r = requests.get(
            'http://user-name:key@'+URL.replace("http://","")+"/api/json")
        return r.json()

def Return_SubJobURL_fromJSON(JSON):
    results = []
    try:
        for elem in JSON["subBuilds"]:
            results.append(elem["url"])
    except:
        pass
    return results

def GetHostname(url):
    try:
        hostname = re.match(r'(.*?)/view/', url).group(1)
    except:
        hostname = re.match(r'(.*?)/job/', url).group(1)
    hostname = hostname.replace("http://", "")
    return hostname

def urlbuilder(path,hostname):
    if path.startswith('job/'):
        url="http://"+hostname+"/"+path
    return url

def get_links_recursive(base, path, visited,max_depth=10, depth=0):
    hostname = GetHostname(base)
    if depth < max_depth:
        try:
            URLS = Return_SubJobURL_fromJSON(ReturnJSONfromURL(base))

            for link in URLS:
                link=urlbuilder(link, hostname)
                if link not in visited:
                    visited.append(link)
                    #print(f"at depth {depth}: {link}")

                    if link.startswith("http"):
                        get_links_recursive(link, "", visited, max_depth, depth + 1)
                    else:
                        get_links_recursive(base, link, visited, max_depth, depth + 1)
        except:
            print("Excepted in Recursive link generator")
            pass
    return visited

def returnPassFailcount(url):

    try:
        JSON = ReturnJSONfromURL(url)
        if JSON["building"]:
            Passed, failCount, Skipped, total = PassFailSkipTestExecutionLog(GetTestExecutionLog(url))
            return ['=HYPERLINK("' + url + '","' + JobNameFromURL(url) + '")',
                    total, Passed, failCount, Skipped, "!!RUNNING RESULT - NOT FINAL"]

        if JSON["result"]=="ABORTED":
            return['=HYPERLINK("'+url+'","'+JobNameFromURL(url)+'")',"ABORTED"]
        else:
            for x in range(len(JSON["actions"])):
                flag=0
                try:
                    if "testngreports" or "robot" in JSON["actions"][x]["urlName"]:
                        total=JSON["actions"][x]["totalCount"]
                        failCount=JSON["actions"][x]["failCount"]
                        Skipped=JSON["actions"][x]["skipCount"]
                        Passed=total-failCount-Skipped
                        flag=1
                        try:
                            return ['=HYPERLINK("'+GetArtifactsRelativeURL(url)+'","'+JobNameFromURL(url)+'")', total, Passed, failCount, Skipped]
                        except:
                            return ['=HYPERLINK("' + url + '","' + JobNameFromURL(url) + '")',
                                    total, Passed, failCount, Skipped]

                except:
                    #handle json path doesnt exist issue when blank sub json
                    pass

            if flag==0:
                try:
                    Passed,failCount,Skipped,total=PassFailSkipTestExecutionLog(GetTestExecutionLog(url))
                    return ['=HYPERLINK("' + url + '","' + JobNameFromURL(url) + '")',
                            total, Passed, failCount, Skipped,"!!Execution log Parsed"]
                    pass
                except:
                    if len(Return_SubJobURL_fromJSON(JSON))==0:
                        return ['=HYPERLINK("'+url+'","'+JobNameFromURL(url)+'")',"!! TestNG Updated ?"]
                    else:
                        return['=HYPERLINK("'+url+'","'+JobNameFromURL(url)+'")',"Master Job"]
    except:
        print("Excepted From returnPassFailcount")
        return ['=HYPERLINK("'+url+'","'+JobNameFromURL(url)+'")']

def RemoveJobCountFromURL(url):
    url = re.sub('/[0-9]+/$', '', url)
    url = re.sub('/[0-9]+$', '', url)
    return url

def GetJobCountFromURL(url):
    try:
        if re.search('/[0-9]+/$', url)!=None:
            url = re.search('/[0-9]+/$', url).group(0)
        elif re.search('/[0-9]+$', url)!=None:
            url = re.search('/[0-9]+$', url).group(0)
        return int(url.replace('/', ''))
    except:
        print("Excepted From Return Job Number From URL : Does your url have job number ??")
        print("Hello")
        print(os.getenv("Parameter 1"))

def GetUpstreamProjects(url):
    url=RemoveJobCountFromURL(url)
    print(url)
    return ReturnJSONfromURL(url)["upstreamProjects"]

def JobNameFromURL(url):
    try:
        JobName = re.findall(r"job/(.*)/",url)
    except:
        JobName = re.findall(r"view/(.*)/",url)
    return JobName[0].split("/", 1)[0]

def CheckPresenceOfSheet(SheetName):
    try:
        sh = client.open(SheetName)
        return True
    except:
        return False

def SubSheetRemover(MainSheet):
    while len(MainSheet.worksheets())>9:
        print("Sub-Sheet Count Limit Exceeded : Deleting Initial Subsheet")
        MainSheet.del_worksheet(MainSheet.worksheets()[0])
        print("deleted SUCCESS")
        time.sleep(2)

def subsheetexist(Mainsheet,Subsheetname):
    try:
        Mainsheet.worksheet(Subsheetname)
        return True
    except:
        return False

def ReturnSheetResultPayload(MasterURLS):
    sheetupdateload = []
    sheetupdateload.append(["URL", "Total", "Passed", "Failed", "Skipped"])
    for url in MasterURLS:
        sheetupdateload.append([])
        print("Crawling Child Jobs....")
        AlljobURLS=get_links_recursive(url, "",[url])
        print(AlljobURLS)
        for alljoburl in AlljobURLS:
            sheetupdateload.append(returnPassFailcount(alljoburl))

    return sheetupdateload

def WriteToSheetName(SheetName,Subsheet,MasterURLS,Email):
    Subsheet.insert_rows(ReturnSheetResultPayload(MasterURLS), value_input_option="USER_ENTERED")
    spreadsheet_url = "https://docs.google.com/spreadsheets/d/%s" % SheetName.id
    try:
        SheetName.share(Email, perm_type='user', role='writer')
    except:
        print("Excepted while sharing to Email")
    print("Sheet Updated with Results, Find results in the following URL")
    print(spreadsheet_url)

def CreateShareClean(MainSheetName,SubsheetName,Folder="drive-folderid"):
    try:
        client.open(MainSheetName)
        CreateShareClean(MainSheetName+time.strftime("%Y%m%d-%H%M%S"),SubsheetName,Folder="drive-folderid")
    except:
        MainSheet = client.create(MainSheetName, Folder)

        # update custom ID in sheet for future cleanups
        if Folder=="drive-folder-id":
            CustomIDSheet=client.open_by_key("key")
            CustomIDSheetworksheet = CustomIDSheet.get_worksheet(0)
            CustomIDSheetworksheet.insert_rows([[MainSheet.id]])

        SubSheet = MainSheet.add_worksheet(SubsheetName, rows="1000", cols="20")
        MainSheet.del_worksheet(MainSheet.worksheet("Sheet1"))
        return (MainSheet,SubSheet)

# !! WARNING ..!! This will delete All subsheets created..!! Run with Higher Auth Permission
def CleanCustomSheets(IDSheet):
    Sheet=client.open_by_key(IDSheet)
    worksheet = Sheet.get_worksheet(0)
    SheetID_list = worksheet.col_values(1)
    for sheetid in SheetID_list:
        client.del_spreadsheet(sheetid)
    worksheet.clear()

def GetArtifactsRelativeURL(url):
    try:
        JSON=ReturnJSONfromURL(url)
        for i in range(len(JSON["artifacts"])):
            if ".html" in JSON["artifacts"][i]["fileName"]:
                return url+"/artifact/"+JSON["artifacts"][i]["relativePath"]
    except:
        print("Excepted While generating Artifacts")
        return ""

def GetTestExecutionLog(buildurl):
    try:
        JSON=ReturnJSONfromURL(buildurl)
        for i in range(len(JSON["artifacts"])):
            if ".log" in JSON["artifacts"][i]["fileName"]:
                return buildurl+"/artifact/"+JSON["artifacts"][i]["relativePath"]
    except:
        print("Excepted While generating TestExecutionLog")
        return ""

def PassFailSkipTestExecutionLog(executionlog):
    output = urlopen(executionlog).read().decode('utf-8')
    AllStatus=re.findall(r',Status : (.*?),Status Reason', output)
    PassCount=Counter(AllStatus)["pass"]
    FailCount = Counter(AllStatus)["fail"]
    SkipCount=Counter(AllStatus)["skip"]
    TotalCount=PassCount+FailCount+SkipCount
    if TotalCount==0:
        PassCount = Counter(AllStatus)["passed"]
        FailCount = Counter(AllStatus)["failed"]
        SkipCount = Counter(AllStatus)["skipped"]
        TotalCount = PassCount + FailCount + SkipCount
    return (PassCount,FailCount,SkipCount,TotalCount)

def main():
    MasterURLS = os.getenv("InputBuildURLs").splitlines()
    SheetName = os.getenv("CustomSheetName")
    SubSheetName = os.getenv("SubSheetName")
    MailID = os.getenv("Email")

    # inputs
    #MasterURLS = ["jenkins url"]
    #SheetName = "test_20220628-115732" #Create Custom Sheet
    #SubSheetName ="CUT new" #Leave Default Unless you want to add on results to same sheet
    #MailID="test@domain.com" #Must Enter To Give Permission


    #If Multiple URL in MasterURLS, We will create a new sheet if sheetname not specified

    # get the instance of the Spreadsheet
    if SheetName=="Default":
        if len(MasterURLS)>1:
            #Case 1 : Multiple Master URL in Input
            WorkSheetName="MultiURL Result"+time.strftime("%Y%m%d-%H%M%S")
            WorkSheetName,SubSheet=CreateShareClean(WorkSheetName, "Sheet 1","sheet-id")
            print("Sheet Created -> Shared (Multiple Master URL)")
            WriteToSheetName(WorkSheetName,SubSheet,MasterURLS,MailID)
        else:
            # Case 2 : Job url without any slave jobs
            # Complete without updating results

            if len(Return_SubJobURL_fromJSON(ReturnJSONfromURL(MasterURLS[0])))==0:
                print("There are no Subjobs in this URL to crawl")

            else:
                # Case 3 : Master URL with 1/more subjobs
                # Reuse sheet | If sheet doesnt exist for master, create and reuse
                # handle case to delete sub sheets when count>9
                # handle case when subsheet already exist

                # Case 3 (i) : Master | Main Sheet Already Exist
                if(CheckPresenceOfSheet(JobNameFromURL(MasterURLS[0]))):
                    SheetName=client.open(JobNameFromURL(MasterURLS[0]))
                    # Case 3 (i)(I) : Master | Main Sheet Already Exist | Subsheet Already Exist - Rewrite
                    if subsheetexist(SheetName,"Run "+str(GetJobCountFromURL(MasterURLS[0]))):
                        SubSheetRemover(SheetName)
                        Subsheet=SheetName.worksheet("Run "+str(GetJobCountFromURL(MasterURLS[0])))
                        print("Subsheet exist, cleaning")
                        Subsheet.clear()
                        print("Writing to Cleaned Sheet")

                        WriteToSheetName(SheetName, Subsheet, MasterURLS,MailID)
                    # Case 3 (i)(I) : Master | Main Sheet Already Exist | Subsheet Doesnt Exist - Create
                    else:
                        print("Subsheet Doesnt Exist")
                        SubSheetRemover(SheetName)
                        Subsheet=SheetName.add_worksheet(title="Run "+str(GetJobCountFromURL(MasterURLS[0])), rows="1000", cols="20")
                        WriteToSheetName(SheetName, Subsheet, MasterURLS,MailID)
                # Case 3 (ii) : Master Main Sheet Doesnt Exist
                else:
                    Mainsheet,Subsheet=CreateShareClean(JobNameFromURL(MasterURLS[0]), "Run "+str(GetJobCountFromURL(MasterURLS[0])))
                    print("SheetDoesntExist - Created")
                    WriteToSheetName(Mainsheet, Subsheet, MasterURLS,MailID)

    elif SheetName!="Default":
        #case user give sheet name, enable user to append results to same sheet
        # check if sheet present -> if present append date time - handled
        if SubSheetName=="Default":
            SubSheetName="Sheet 1"
            if CheckPresenceOfSheet(SheetName):
                print("!!!! WARNING !!!!")
                print("A Sheet With this name already exist..!! You Selected Default in Subsheet,"
                      " So you are not adding to the same sheet")
                print("We will create a new unique sheet with this name appended for you..!!")
                Mainsheet, Subsheet = CreateShareClean(SheetName+"_"+time.strftime("%Y%m%d-%H%M%S"), SubSheetName, "sheet-id")
                WriteToSheetName(Mainsheet, Subsheet, MasterURLS, MailID)
                return

        if CheckPresenceOfSheet(SheetName):
            print("WARNING>>!! Sheet Already Exist.. Will create subsheet within sheet")
            Mainsheet=client.open(SheetName)
            if subsheetexist(Mainsheet,SubSheetName):
                print("Subsheet Already Exist in this sheet..!! Try Other Name")
                return()
            SubSheet = Mainsheet.add_worksheet(SubSheetName, rows="1000", cols="20")
            WriteToSheetName(Mainsheet, SubSheet, MasterURLS,MailID)
        else:
            Mainsheet, Subsheet = CreateShareClean(SheetName, SubSheetName,"sheet-id")
            WriteToSheetName(Mainsheet, Subsheet, MasterURLS,MailID)






if __name__ == "__main__":
    main()











