from os.path import basename,dirname,abspath
GH_CMSSW_ORGANIZATION="Mu2e"
GH_CMSSW_REPO="Offline"


#This is overridden by GITHUBTOKEN env var
GH_TOKEN="~/.github-token-FNALbuild"
#This is overridden by GITHUBTOKEN env var

GH_TOKEN_READONLY="~/.github-token-readonly"
CONFIG_DIR=dirname(abspath(__file__))

#GH bot user: Use default FNALbuild
CMSBUILD_USER="FNALbuild"
CMSBUILD_GH_USER = CMSBUILD_USER

GH_REPO_ORGANIZATION=basename(dirname(CONFIG_DIR))
GH_REPO_FULLNAME="Mu2e/Offline"
CREATE_EXTERNAL_ISSUE=False

#Jenkins CI server: User default http://cmsjenkins05.cern.ch:8080/cms-jenkins
JENKINS_SERVER="https://buildmaster.fnal.gov/buildmaster"

#GH Web hook pass phrase. This is encrypeted used bot keys.
GITHUB_WEBHOOK_TOKEN="""U2FsdGVkX19PBZ+7mbii/zhgnEfFubgVOlQdma65gS0WQC9S4E6xzMvlCEGdLdzZ
Z7/Stk/oQHs+u669dPQm+g=="""

#Set to True if you want bot to add build/test labels to your repo
ADD_LABELS=True
#Set to True if you want bot to add GH webhooks. FNALbuild needs admin rights
ADD_WEB_HOOK=True

#For cmsdist/cmssw repos , set it to False if you do not want to run standard cms pr tests
CMS_STANDARD_TESTS=False
#Map your branches with cmssw branches for tests
#User Branch => CMSSW/CMSDIST Branch
CMS_BRANCH_MAP={
}
VALID_WEB_HOOKS=["issues","pull_request","issue_comment"]
