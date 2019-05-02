from __future__ import print_function
import pickle
import os
import subprocess
import requests
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from Naked.toolshed.shell import execute_js
from git import Repo
#import virtualenv
import pip
import json
import xml.etree.ElementTree as ET
import traceback
import shutil


PYLIBSURL = 'https://hugovk.github.io/top-pypi-packages/top-pypi-packages-365-days.min.json'

def findTestPath(repoPath):
    for (dirpath, dirnames, filenames) in os.walk(repoPath):
        for folder in dirnames:
            if folder == 'tests' or folder == 'test':
                return os.path.join(dirpath, folder)
    return None

def findRequirements(repoPath):
    reqs = []
    for (dirpath, dirnames, filenames) in os.walk(repoPath):
        for file in filenames:
            if file.startswith('requirements'):
                reqs.append(os.path.join(dirpath, file))
        break
    return reqs

def buildSheetsService():
        # If modifying these scopes, delete the file token.pickle.
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

        # Build Google sheets service
        creds = None
        # The file token.pickle stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists('creds/token.pickle'):
            with open('creds/token.pickle', 'rb') as token:
                creds = pickle.load(token)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'creds/credentials.json', SCOPES)
                creds = flow.run_local_server()
            # Save the credentials for the next run
            with open('creds/token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        return build('sheets', 'v4', credentials=creds)

class CodeCov:
    def __init__(self, name, downloads, googleService):
        self.repoName = name
        self.downloads = downloads
        self.repoPath = '/home/mathius/Documents/CS5850/DataRetrieval/RepoDir/' + name
        self.repoUrl = None
        self.gitToken = None

        self.googleService = googleService
        self.tempEnvDir = os.path.join(os.path.expanduser("~"), ".codecov")
        
        self.data = []

    def setup(self):
        f = open('creds/github-token.txt','r')
        self.gitToken = f.read()
        
        # create a virtualenv at ~/.codecov
#         if not os.path.exists(self.tempEnvDir):
#             virtualenv.create_environment(self.tempEnvDir)
#         activate_script = os.path.join(self.tempEnvDir, "bin", "activate_this.py")
#         exec(compile(open(activate_script, "rb").read(), activate_script, 'exec'), 
#              dict(__file__=activate_script))

    def retrieveRepo(self):
        url = 'https://api.github.com/search/repositories?q=' + self.repoName
        headers= {'Authorization': 'token ' + self.gitToken}
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            raise Exception('Failed while getting repo data from Github API')
        self.repoUrl = r.json()['items'][0]['full_name']
        Repo.clone_from('https://github.com/' + self.repoUrl, self.repoPath)

    def setupRepo(self):
        reqFilePaths = findRequirements(self.repoPath)
        for filePath in reqFilePaths:
            with open(filePath) as f:
                for line in f:
                    # call pip's main function with each requirement
                    try:
                    	pip.main(['install','-U', line])
                    except:
                    	print('Failed to install: ' + line)
        
    def runTests(self):
        test_path = findTestPath(self.repoPath)

        if test_path == None:
            raise Exception('Failed to find test directory')

        cmd = ['coverage', 'run', '-m', 'pytest', test_path]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        o, e = proc.communicate()

        # print('Output: ' + o.decode('ascii'))
        # print('Error: '  + e.decode('ascii'))
        # print('code: ' + str(proc.returncode))

        # Failed to find pytest tests
        if proc.returncode != 0:
            cmd = ['coverage', 'run', '-m', 'unittest', 'discover', '-s', test_path]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            o, e = proc.communicate()
            if proc.returncode != 0:
                raise Exception("Failed to run tests")

        cmd = ['coverage', 'xml', '-o', 'resources/coverage.xml']
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        o, e = proc.communicate()

        if proc.returncode != 0:
            raise Exception("Failed to create coverage report")

    def scrape(self):
        success = execute_js('scrape.js', arguments=self.repoUrl)
        if not success:
            raise Exception("Failed while scraping Github")

    def organizeData(self):
        self.data.append(self.repoName)
        
        #coverage.xml
        tree = ET.parse('resources/coverage.xml')
        root = tree.getroot()
        
        #lines evaluated & percent covered
        self.data.append(root.items()[6][1])
        self.data.append(root.items()[4][1])
        
        self.data.append(self.downloads)
        
        fileName = self.repoUrl.split('/')[0] + '-' + self.repoUrl.split('/')[1]
        with open('scrapes/' + fileName + '.json', 'r') as json_file:  
            data = json.load(json_file)
            self.data.append(data['watchers'])
            self.data.append(data['forks'])
            self.data.append(data['commits'])
            self.data.append(data['branches'])
            self.data.append(data['releases'])
            self.data.append(data['stars'])

    def addToSheets(self):
        # The ID and range of a sample spreadsheet.
        spreadsheet_id = '1nhttU75rL_9gRf-Awr7YojMuPTIVyrDMxpHfaThJm6E'
        range_ = 'Sheet1!A1:E1'
        value_input_option = 'RAW'
        insert_data_option = 'INSERT_ROWS'

        values = [self.data]
        value_range_body = {
            'values': values
        }

        request = self.googleService.spreadsheets().values().append( \
                        spreadsheetId=spreadsheet_id, 
                        range=range_, 
                        valueInputOption=value_input_option, 
                        insertDataOption=insert_data_option, 
                        body=value_range_body)

        response = request.execute()
        return response
    
    def tearDown(self):
        #os.system('deactivate')
        try:
            #shutil.rmtree(self.tempEnvDir)
            if os.path.isdir(self.repoPath):
            	shutil.rmtree(self.repoPath)
            if os.path.isdir('resources'):
            	shutil.rmtree('resources')
            if os.path.isdir('.hypothesis'):
            	shutil.rmtree('.hypothesis')
            if os.path.exists('.coverage'):
            	os.remove('.coverage')
        except OSError as e:
            print ("Error: %s - %s." % (e.filename, e.strerror))
            raise e
        #TODO: erase temp files

def main():
	googleService = buildSheetsService()
	r = requests.get(PYLIBSURL).json()
	if not os.path.isdir("resources/"):
		os.mkdir('resources')
	with open('resources/python-libs.json', 'w') as f:
		json.dump(r, f)
    
	count = 0
	for row in r['rows']:
		if count == 10:
			break
		count += 1
		codeCov = CodeCov(row['project'], int(row['download_count']), googleService)
		try:
			codeCov.setup()
			codeCov.retrieveRepo()
			codeCov.setupRepo()
			codeCov.runTests()
			codeCov.scrape()
			codeCov.organizeData()
			codeCov.addToSheets()
		except Exception as e:
			print(traceback.format_exc())

		try:
			codeCov.tearDown()
		except Exception as e:
			print(traceback.format_exc())
			break

if __name__ == '__main__':
    main()