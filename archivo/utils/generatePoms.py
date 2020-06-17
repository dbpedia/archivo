import os
import sys
import subprocess
from utils import stringTools
from utils import archivoConfig

def generateParentPom(groupId, packaging, modules, packageDirectory, downloadUrlPath, publisher, maintainer, groupdocu, license=archivoConfig.default_license, deployRepoURL=archivoConfig.default_repo, version=archivoConfig.default_version, artifactId=archivoConfig.default_parentArtifact):

    modlueStrings = [f"    <module>{module}</module>" for module in modules]
    
    if modules == []:
        moduleString = ""
    else:
        moduleString = "   <modules>\n"+"\n".join(modlueStrings)+"\n   </modules>\n "

    return ('<?xml version="1.0" encoding="UTF-8"?>  \n'  
    '<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"  \n'  
    '            xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">  \n'  
    '   <modelVersion>4.0.0</modelVersion>  \n'  
    '   <parent>  \n'  
    '       <groupId>org.dbpedia.databus</groupId>  \n'  
    '       <artifactId>super-pom</artifactId> \n '  
    '       <version>1.3-SNAPSHOT</version>  \n'  
    '   </parent>  \n'  
    '     \n'  
    f'  <groupId>{groupId}</groupId>  \n'  
    f'  <artifactId>{artifactId}</artifactId>  \n'  
    f'  <packaging>{packaging}</packaging>  \n'  
    f'  <version>{version}</version> \n '  
    f'{moduleString}'  
    '   <properties>  \n'  
    '       <databus.tryVersionAsIssuedDate>false</databus.tryVersionAsIssuedDate>  \n'  
    '       <databus.packageDirectory>  \n'  
    f'          {packageDirectory} \n '  
    '       </databus.packageDirectory>  \n'   
    '       <databus.pkcs12File>${user.home}/.m2/onto_webid_bundle.p12</databus.pkcs12File>  \n'  
    '       <databus.downloadUrlPath>  \n'  
    f'          {downloadUrlPath} \n '  
    '       </databus.downloadUrlPath>  \n'  
    f'       <databus.deployRepoURL>{deployRepoURL}</databus.deployRepoURL>  \n'  
    f'       <databus.publisher>{publisher}</databus.publisher>  \n'  
    f'       <databus.maintainer>{maintainer}</databus.maintainer>  \n'  
    f'       <databus.license>{license}</databus.license>  \n'  
    '       <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>  \n'  
    '       <databus.documentation><![CDATA[\n'
    f'      {groupdocu}\n'    
    '       ]]></databus.documentation>  \n'  
    '   </properties>  \n'  
    '     \n'  
    '   <!-- currently still needed to find the super-pom, once the super-pom is in maven central,  \n'  
    '       this can be removed as well -->  \n'  
    '   <repositories>  \n'  
    '       <repository>  \n'  
    '           <id>archiva.internal</id>  \n'  
    '           <name>Internal Release Repository</name>  \n'  
    '           <url>http://databus.dbpedia.org:8081/repository/internal</url>  \n'   
    '       </repository>  \n'  
    '       <repository>  \n'   
    '           <id>archiva.snapshots</id>  \n'  
    '           <name>Internal Snapshot Repository</name>  \n'   
    '           <url>http://databus.dbpedia.org:8081/repository/snapshots</url>  \n'  
    '           <snapshots>  \n'  
    '               <updatePolicy>always</updatePolicy>  \n'  
    '           </snapshots>  \n'  
    '       </repository>  \n'  
    '   </repositories>  \n'  
    '     \n'  
    '</project>  \n')  

def generateChildPom(groupId, artifactId, packaging, version, license=None, parentArtifactId=archivoConfig.default_parentArtifact, parentVersion=archivoConfig.default_version):
    if version == None or version == "":
        versionString = ""
    else:
        versionString = f"<version>{version}</version>\n"

    if license == None or license == "":
        licenseString = ""
    else:
        licenseString = (
                        '   <properties>\n'
                        f'      <databus.license>{license}</databus.license>\n'
                        '   </properties>\n'
                        )
    return ('<?xml version="1.0" ?>  '  
        '<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">  \n'  
        '\n'  
        '\n'  
        '   <parent>  \n'   
        f'      <groupId>{groupId}</groupId>  \n'  
        '\n'    
        f'      <artifactId>{parentArtifactId}</artifactId>  \n'  
        '\n'  
        f'      <version>{parentVersion}</version>  \n'  
        '\n'  
        '   </parent>  \n'  
        '\n'  
        '   <modelVersion>4.0.0</modelVersion>  \n'  
        '\n'  
        f'   {versionString}'
        '\n'
        f'   <groupId>{groupId}</groupId>  \n' 
        '\n'    
        f'   <artifactId>{artifactId}</artifactId>  \n'  
        '\n'  
        f'   <packaging>{packaging}</packaging>  \n'  
        '\n'
        f'{licenseString}' 
        '</project>\n')


def writeMarkdownDescription(path, artifact, label, explaination, description=""):

    with open(path  + os.sep + artifact + ".md", "w+") as mdfile:
        mdstring=(f"# {label}\n"
            f"{explaination}\n"
            "\n"
            f"{description}")
        print(mdstring, file=mdfile)

def callMaven(pomfilePath, command):
    process = subprocess.Popen(["mvn", "-B", "-f", pomfilePath, command], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    print(stderr.decode("utf-8"))
    return process.returncode, stdout.decode("utf-8")


def updateParentPoms(rootdir, index):
    
    for uri in index:
        group, artifact = stringTools.generateGroupAndArtifactFromUri(uri)

        parentPomPath = os.path.join(rootdir, group, "pom.xml")
        if not os.path.exists(parentPomPath):
            print("Couldnt find parent pom for", uri, file=sys.stderr)
            continue
        artifactDirs = [dir for dir in os.listdir(os.path.join(rootdir, group)) if os.path.isdir(os.path.join(rootdir, group, dir)) and os.path.isfile(os.path.join(rootdir, group, dir, "pom.xml"))]

        if artifactDirs == []:
            print("No artifacts for", uri, file=sys.stderr)
            continue

        with open(parentPomPath, "w+") as parentPomFile:
            pomstring = generateParentPom(
                                groupId=group,
                                packaging="pom",
                                modules=artifactDirs,
                                packageDirectory=archivoConfig.packDir,
                                downloadUrlPath=archivoConfig.downloadUrl,
                                publisher=archivoConfig.pub,
                                maintainer=archivoConfig.pub,
                                groupdocu=archivoConfig.groupDoc.format(group),
                                )
            print(pomstring, file=parentPomFile)    

