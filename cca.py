#
#        PICOtron
#        ========
#
#   converts all intervention reviews from input folder
#   to html documents in output folder
#
#


import glob
from xml.dom import minidom
from datetime import datetime
import codecs
from bs4 import BeautifulSoup
from decimal import *
import os
import re
import random
import collections
import codecs
import progressbar
from csv import DictReader



# *** CONSTANTS ***




# TODO!! add to to assess this automatically
# need to have constant denominator across whole CCA
# dependant on whether *any* analyses have an AR < 1 in 100
DENOMINATOR = 1000 # 100 is default; 1000 in rare cases where small ARs




# path variables
PATH = {}
PATH["rev"] = "input/"  # input directory
PATH["op"] = "output/" # output directory



DISPLAY_COMMENTS = False # display compiler comments
ABS_IF_SIG_ONLY = False # display absolute numbers only where significant result
PICOTRON_VERSION = "28"


# templates
HTML_HEADER = """
<html>

    <head>
        <title></title>
        <meta name="GENERATOR" CONTENT="the PICOtron">
        <meta http-equiv="content-type" content="text/html; charset="utf-8">
        <style type="text/css">
        <!--
            body { font-family: Calibri, Arial; font-size: 10pt;}
            p.MsoNormal, li.MsoNormal, div.MsoNormal {font-size:10.0pt; font-family:Calibri;}
            h1, h3, h4 { font-family: Calibri, Arial;}
            h1 { color: #394F91;}
            p { font-size: 10pt;}
            h3 { font-size: 12pt;}
            h4 { font-size: 10pt;}
            ul, li { font-size: 10pt;}
            table { border-collapse: collapse; border-style: solid; border-color: #444444; border-width: 1px; width:100%;}
            td, th { vertical-align: top; height: 100%; border-color: #444444; border-style: solid; border-width: 1px;}
            .leftcol {width:200px;}
            .compiler {color: #0096FF;}
            .edittext {color: #0096FF;}
        -->
        </style>
    </head>
    <body>
"""

TABLE_HEADER = """
        <table>
"""

TABLE_FOOTER = """
        </table>
"""


HTML_FOOTER = """
    </body>
</html>
"""

INTRO = """
 PICO generator
"""


QUESTION_PATTERNS = [['What are the effects of intname in people with cndname?', 'What are the benefits and harms of intname in people with cndname?'],
['What are the effects of intname in popname with cndname?', 'What are the benefits and harms of intname in popname with intname?'],
['How does intname compare with cntname in people with cndname?'],
 ['How does intname compare with cntname] in popname with cndname?']]


# vocabulary

UNIT_DICT = {"MD": "mean difference", "SMD": "standardized mean difference", "PETO_OR": "Peto OR", "RELATIVE RISK": "RR", "ODDS RATIO": "OR", "RISK RATIO": "RR", "HAZARD RATIO": "HR"}
WORD_NUM_DICT = {"1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine", "10": "ten"}
ORDINAL_NUM_DICT = {"1": "first", "2": "second", "3": "third", "4": "fourth", "5": "fifth", "6": "sixth", "7": "seventh", "8": "eighth", "9": "ninth", "10": "tenth", "11": "eleventh", "12": "twelfth"}
ORDINAL_ENDING_DICT = {"1": "st", "2": "nd", "3": "rd"}

VOWELS = "aeiou"
CONSONANTS = "bcdfghjklmnpqrstvwxyz"

DONT_CONVERT_TO_LOWER = ["VAS", "VAS.", "NSAID", "LABA", "ICS", "PEF", "FEV", "RCT", "TCC", "FEV1"]

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

ERROR_LOG = []





# *** FUNCTIONS FOR PARSING THE BROWSE MENU ***


def get_topic_filename():    
    return os.path.join(PATH["rev"], "topics.csv")


def parse_topics(filename):
    " takes a csv file, parses, and returns a dict of sets of top level headings (in case more than one) "
    topic_lookup = collections.defaultdict(set)

    with open(filename, 'rU') as f:
        csv_file = DictReader(f, dialect='excel')
        for line in csv_file:
            topic_lookup[line["CD Number"]].add(line["Level 1"])

    return topic_lookup


# *** FUNCTIONS FOR SIMPLE LANGUAGE PARSING ***

def numberword(noun, number):
    " returns an appropriately pluralised word with the formatted number in front "
    number = str(number)
    if number == "0":
        return "no " + pluralise(noun)
    elif number == "1":
        return "one " + noun
    elif number in WORD_NUM_DICT:
        return WORD_NUM_DICT[number] + " " + pluralise(noun)
    else:
        return number + " " + pluralise(noun)

def ordinalnumber(number):
    " gets ordinal number in words from integer "
    number = str(number)
    return ORDINAL_NUM_DICT.get(number, "%d%s" % (number, ORDINAL_ENDING_DICT.get(number[-1], "th")))

def pluralise(word):
    " rule-based generation of plurals from a single word as a string "
    wordl = word.lower()

    if wordl[-1:] in ["s", "x", "o"] or wordl[-2:] in ["ch", "sh"]:
        return word + "es"
    elif wordl[-1:] == "f":
        return word [:-1] + "ves"
    elif wordl[-2:] == "fe":
        return word [:-2] + "ves"
    elif wordl[-1:] == "y" and wordl[-2:-1] not in VOWELS:
        return word[:-1] + "ies"
    else:
        return word + "s"

def mid_sent(txt):
    " capitalises a word when mid_sentence "
    words = txt.split(' ')
    op = []
    for word in words:
        if word in DONT_CONVERT_TO_LOWER:
            op.append(word)
        else:
            op.append(word.lower())
    return " ".join(op)

def start_sent(txt):
    " capitalises for start of sentence "
    return txt[0].upper() + txt[1:]


def favours_parser(favours_pre):
    """
    checks if Forest plot labels are in predictable form, then changes to editorial preferred sentence "in favour of..."
    generates error if string < 7 characters
    """

    lc = favours_pre.lower()

    if "control" in lc or "experimental" in lc or "treatment" in lc or "intervention" in lc:
        favours_pre += " <span class='edittext'>ALERT! - default 'favored' text left here by authors - please check and change to favoured intervention name if needed</span>"

    if len(favours_pre) < 7:
        return "<span class='edittext'>ALERT! - expected Forest plot key to start with 'favors', instead found - '" + favours_pre + "' - please add text 'in favor of [favoured intervention]'</span>"
    # first check for English or US spelling at start of word
    elif favours_pre[:7].lower() == "favours":
        return "in favor of" + favours_pre[7:]
    elif favours_pre[:6].lower() == "favors":
        return "in favor of" + favours_pre[6:]
    else:
        return "<span class='edittext'>ALERT! - expected Forest plot key to start with 'favors', instead found - '" + favours_pre + "' - please add text 'in favor of [favored intervention]'</span>"



# *** XML HELPER FUNCTIONS ***


def xml_tag_contents(xml, tag, silentfail = False):
    """
     gets first instance of an xml tag (use for unique tag ids)
     and returns contents formatted as string
     or html error message
    """

    els = xml.getElementsByTagName(tag)

    if len(els) > 0:
        return ('').join([node.toxml() for node in els[0].childNodes])
    else:
        if silentfail == False:
            return "<span class='edittext'>The tag " + tag + " was not found in the source RevMan file</span>"
        else:
            return None

def xml_attribute_contents(xml, tag, silentfail = False):
    """
    gets an attribute of an xml tag (use for unique tag ids)
    and returns contents formatted as string
    or html error message
    """
    try:
        r = xml.attributes[tag].value
    except:
        if silentfail == False:
            r = "<span class='edittext'>The tag " + tag + " was not found in the source RevMan file</span>"
        else:
            r = None
    return r

def rm_is_intervention_review(xml):
    " returns True for intervention reviews only "
    cr = xml.getElementsByTagName('COCHRANE_REVIEW')
    review_type=cr[0].attributes['TYPE'].value
    return review_type == 'INTERVENTION'


def ocparse(xml, checkfav = True):
    "takes xml.dom object containing a dichotomous or continuous outcome, returns tuple of values, or None if not estimible"

    name = xml_tag_contents(xml, 'NAME') # analysis name

    if checkfav:
        # find which intervention is favoured by examining forest plot labels
        # (since some outcomes better increased, some better reduced)
        favours1 = xml_tag_contents(xml, 'GRAPH_LABEL_1')
        favours2 = xml_tag_contents(xml, 'GRAPH_LABEL_2')
    else:
        favours1 = ""
        favours2 = ""

    studies=xml.attributes['STUDIES'].value
    octype = xml.nodeName # Dichotomous, Continuous, or IV

    units = xml_attribute_contents(xml, "EFFECT_MEASURE", silentfail = True)
    if units == None:
        try:
            units = xml.getElementsByTagName("EFFECT_MEASURE")[0].firstChild.data
        except:
            units = "No units found"

    if xml.attributes['ESTIMABLE'].value == "NO":
        # where there is *no* meta-analysis, just individual study reports

        ind_study_data=[i for i in xml.childNodes if i.nodeName in ["DICH_DATA", "CONT_DATA"]]

        no_studies = len(ind_study_data)

        if no_studies == 1:
            # where there is only one study, report the results from this
            # in the standard way
            point = Decimal(xml_attribute_contents(ind_study_data[0], 'EFFECT_SIZE'))
            ci95low = Decimal(xml_attribute_contents(ind_study_data[0], 'CI_START'))
            ci95up = Decimal(xml_attribute_contents(ind_study_data[0], 'CI_END'))
            totalInt = xml_attribute_contents(ind_study_data[0], 'TOTAL_1')
            totalCnt = xml_attribute_contents(ind_study_data[0], 'TOTAL_2')
            studies = xml_attribute_contents(xml, 'STUDIES')
            usetotal = xml_attribute_contents(ind_study_data[0], 'TOTALS')
            subgroups = xml_attribute_contents(xml, 'SUBGROUPS')
        else:
            if no_studies > 1:
                # for more than one study; output results of individual studies
                study_text = singlestudiesparse(ind_study_data, units)
            else:
                # for analyses with no studies
                study_text = "no individual studies reported for this analysis (there may be subgroups)."

            subgroups = xml_attribute_contents(xml, 'SUBGROUPS')

            return (None, name, units, None, None, None, favours1, favours2, studies, None, None, subgroups, study_text)
    else:
        # where there is a meta-analysis get these results
        point = Decimal(xml_attribute_contents(xml, 'EFFECT_SIZE'))
        ci95low = Decimal(xml_attribute_contents(xml, 'CI_START'))
        ci95up = Decimal(xml_attribute_contents(xml, 'CI_END'))
        totalInt=xml_attribute_contents(xml, 'TOTAL_1')
        totalCnt=xml_attribute_contents(xml, 'TOTAL_2')
        studies=xml_attribute_contents(xml, 'STUDIES')
        usetotal=xml_attribute_contents(xml, 'TOTALS')
        subgroups=xml_attribute_contents(xml, 'SUBGROUPS')


    participants=int(totalInt)+int(totalCnt) # total participants (in both arms)

    if units.upper() in UNIT_DICT: # standardise units
        units = UNIT_DICT[units.upper()]

    return (octype, name, units, point, ci95low, ci95up, favours1, favours2, studies, participants, usetotal, subgroups, None)


def ier(cer, units, point):
    """
    input:
        cer = absolute risk with control (calculated; from 0 to 1)
        units = RR/OR etc as string
        point = relative risk with intervention (direct from meta-analysis)
    output:
        absolute risk with intervention
        OR None if units not understood
    """
    if units[-2:] == "RR":
        return cer * point
    elif units[-2:] == "OR":

        return cer * (point/(1 - (cer * (1 - point))))
    else:
        return None

def natfreq (risk, denom):
    """
    converts an absolute risk (from 0 to 1)
    to natural frequencies (1 in 100 etc.)
    outputs as string
    """
    return natfreq_nodenom(risk, denom) + " per " + str(denom) + " people"

def natfreq_nodenom (risk, denom):
    """
    gets numerator for natural frequency calculation
    """
    return str((risk * denom).quantize(Decimal("1")))


def singlestudiesparse(studies, units):
    " returns a simple fomatted string containing the results of individual studies for when there is no meta-analysis "
    output = []

    for i, study in enumerate(studies):

        ci95up = Decimal(study.attributes['CI_END'].value)
        ci95low = Decimal(study.attributes['CI_START'].value)
        point = Decimal(study.attributes['EFFECT_SIZE'].value)

        output.append("Study %d: %s %.2f, 95%% CI %.2f to %.2f" % (i+1, units, point, ci95low, ci95up))

    return "; ".join(output)



def cerparse(xml):
    """
    returns a weighted median (as decimal object) of the control absolute risks in the analysis
    weighted by population size
    """

    data = xml.getElementsByTagName('DICH_DATA')

    studydata = []
    total = 0

    for datum in data:
        int_n = Decimal(datum.attributes['EVENTS_1'].value)
        cnt_n = Decimal(datum.attributes['EVENTS_2'].value)
        int_d = Decimal(datum.attributes['TOTAL_1'].value)
        cnt_d = Decimal(datum.attributes['TOTAL_2'].value)
        study_cer = cnt_n / cnt_d # find the cer for each study
        studydata.append((study_cer, int_d + cnt_d)) # then add to a list
        total += (int_d + cnt_d) # and the total population for weighting purpose


    studydata = sorted(studydata)

    midpoint = total / 2 # find the midpoint of the studies weighted by size

    cer = None

    counter = 0
    for (study_cer, total) in studydata: #then run through again, stopping when pass the midway point

        if (counter < midpoint):
            cer = study_cer
        counter += total

    return cer


#####
##
##  FUNCTIONS NO LONGER USED FOR ESTIMATING ABSOLUTE EFFECTS FROM CONTINUOUS OUTCOMES
##
#####


# def cntmeanparse(xml):
#   """
#   returns a weighted median (as decimal object) for control group mean from an xml.dom object containing continuous outcomes
#   weighted by population size
#   """
#   ####
#   ## NO LONGER USED!
#   ####

#     data = xml.getElementsByTagName('CONT_DATA')

#     studydata = []
#     total = 0

#     for datum in data:
#         cnt_m = Decimal(datum.attributes['MEAN_2'].value)
#         int_d = Decimal(datum.attributes['TOTAL_1'].value)
#         cnt_d = Decimal(datum.attributes['TOTAL_2'].value)

#         studydata.append((cnt_m, int_d + cnt_d)) # then add to a list
#         total += (int_d + cnt_d) # and the total population for weighting purpose

#     studydata = sorted(studydata)

#     midpoint = total / 2 # find the midpoint of the studies weighted by size

#     cntmean = None
#     counter = 0

#     for (study_cntmean, total) in studydata: #then run through again, stopping when pass the midway point

#         if (counter < midpoint):
#             cntmean = study_cntmean
#         counter += total

#     return cntmean




# def intmeanparse(xml):
#   """
#   returns a weighted median (as decimal object) for control group mean from an xml.dom object containing continuous outcome
#   """

#   ####
#   ## NO LONGER USED!
#   ####

#     data = xml.getElementsByTagName('CONT_DATA')

#     studydata = []
#     total = 0

#     for datum in data:
#         int_m = Decimal(datum.attributes['MEAN_1'].value)
#         cnt_m = Decimal(datum.attributes['MEAN_2'].value)
#         int_d = Decimal(datum.attributes['TOTAL_1'].value)
#         cnt_d = Decimal(datum.attributes['TOTAL_2'].value)

#         studydata.append((cnt_m, int_m, total)) # then add to a list
#         total += (int_d + cnt_d) # and the total population for weighting purpose

#     studydata = sorted(studydata)

#     midpoint = total / 2 # find the midpoint of the studies weighted by size

#     intmean = None

#     for (study_cntmean, study_intmean, total) in studydata: #then run through again, stopping when pass the midway point

#         if (total < midpoint):
#             intmean = study_intmean

#     return intmean


# def int_mean(cer_mean, dif):
#   """
#   estimates mean differences given these values
#   """
#   ####
#   ## NO LONGER USED!
#   ####
#     return (cer_mean + dif).quantize(Decimal('.01'))



# def rm_mean_values(octype, intname, cntname, name, units, point, ci95low, ci95up, studies, participants, xml): # returns nice bit of absolute value text for an xml.dom obj, (dich outcome)
#   ####
#   ## NO LONGER USED!
#   ####

#     cutoff = 0

#     if (Decimal(ci95low) < cutoff) and (Decimal(ci95up) > cutoff) and ABS_IF_SIG_ONLY:

#         aresult = "There was no statistically significant difference between groups."
#     else:

#         cntmean = cntmeanparse(xml)
#         intmean = int_mean(cntmean, point)
#         meanci95low = int_mean(cntmean, ci95low)
#         meanci95up = int_mean(cntmean, ci95up)


#         aresult =  str(intmean) + " (between " + str(meanci95low) + " and " + str(meanci95up) + ") with " + mid_sent(intname) + " compared with " + str(cntmean) + " with " + mid_sent(cntname) + "."



#     return aresult


def rm_abs_values(octype, intname, cntname, name, units, point, ci95low, ci95up, studies, participants, xml):
    """
    returns absolute value text for an xml.dom obj, (dich outcome)
    """

    # set significance cutoff
    if units[-1] == "R" or units.upper()[-10:] == "RATE RATIO":
        cutoff = 1
    else:
        cutoff = 0



    if (Decimal(ci95low) == 0) and (Decimal(point) == 0) and (Decimal(ci95up) == 0):
        # error from malformed RM5 - authors not completed fields
        aresult = "ERROR - No absolute result possible since effect size and 95% CI set to 0."
    elif (Decimal(ci95low) < cutoff) and (Decimal(ci95up) > cutoff) and ABS_IF_SIG_ONLY:
        # result is not significant
        aresult = "There was no statistically significant difference between groups."
    else:
        # result is significant

        # calculate absolute risks and 95% CIs for intervention group
        abcer = cerparse(xml)
        abier = ier(abcer, units, point)

        abci95low = ier(abcer, units, ci95low)
        abci95up = ier(abcer, units, ci95up)


        # NO LONGER REQUIRED - need to have constant denominator across whole CCA
        # dependant on whether *any* analyses have an AR < 1 in 100
        #
        # give absolute frequencies out of 1000 if fewer than 1 in 100 in either group
        # if (0 < abcer < 0.01) or (0 < abier < 0.01):
        #     denom = 1000
        # else:
        #     denom = 100

        # TODO!! - add code to choose a CCA-wide denominator - for now is constant
        denom = DENOMINATOR # change based on what is needed

        aresult =  natfreq(abier, denom) + " (95% CI " + natfreq_nodenom(abci95low, denom) + " to " + natfreq_nodenom(abci95up, denom) + ") with " + mid_sent(intname) + " compared with " + natfreq(abcer ,denom) + " with " + mid_sent(cntname) + "."


    return aresult




def rm_unique(xml):
    """ attempts to get CD number from XML (parses from  string) """
    ###
    # TODO can get CD number reliably from XML filename
    ###
    cr = xml.getElementsByTagName('COCHRANE_REVIEW')
    doi = cr[0].attributes['DOI'].value
    doi_l = doi.split('.')

    for d in doi_l:
        if d[:2] == "CD":
            return d
    return "[no CD number found in revman file]"



def rm_title(xml):
    " retrieves review title => string "
    cover = xml.getElementsByTagName('COVER_SHEET')
    title = cover[0].getElementsByTagName('TITLE')
    t = title[0].firstChild.data

    # OLD CODE FOR GENERATING A QUESTION
    #t = t[0].lower() + t[1:]
    #return "What are the effects of " + t + "?" # previously converted to question, new version simply reports original title

    return t


def splitter(n):
    """
    first split into A and B removing the word ' for ' if present
    if no ' for ' always generates an error
    """


    list1 = n.split(' for ')
    if len(list1) is not 2: # if not exactly 2 returned parts return error
        return (None, None, None, None, None)

    a = list1[0] #list is working variable, not used outside fn
    b = list1[1]

    patternno = 0

    if ' in ' in b:
        list1 = b.split(' in ')
        cndname = list1[0]
        popname = list1[1]
        patternno += 1
    else:
        cndname = b
        popname = None


    if ' versus ' in a:
        list1 = a.split(' versus ')
        intname = list1[0]
        cntname = list1[1]
        patternno += 2
    else:
        intname = a
        cntname = None
    return (intname, cntname, cndname, popname, patternno)


def randomquestion(intname, cntname, cndname, popname, patternno):
    """
    makes an arbitrary question from a simple parse of the review title
    (not for publication - as a hint for editors to turn into proper English!)
    """

    random.seed()
    patternpointer = QUESTION_PATTERNS[patternno]
    tmpind = random.randint(0, len(patternpointer) - 1)

    text = patternpointer[tmpind]

    text = re.sub("intname", intname, text) # sub the intervention for intname
    text = re.sub("cndname", cndname, text) # sub the condition for cndname

    if cntname:
        text = re.sub("cntname", cntname, text) # sub the intervention for cntname

    if popname:
        text = re.sub("popname", popname, text) # sub the intervention for popname

    return  text



def rm_overview_p(xml):
    " get inclusion criteria for participants "
    return xml_tag_contents(xml, 'CRIT_PARTICIPANTS')


def rm_overview_i(xml):
    " get inclusion criteria for interventions of interest "
    return xml_tag_contents(xml, 'CRIT_INTERVENTIONS')


def rm_summaryshort(xml):
    "retrieves a short summary (conclusion from the abstract), returns html tagged"
    return xml_tag_contents(xml, 'ABS_CONCLUSIONS')


def rm_implications(xml):
    "retrieves the clinical implications, returns html tagged"
    return xml_tag_contents(xml, 'IMPLICATIONS_PRACTICE')


def rm_summarylong(xml):
    " retrieves the clinical implications, returns html tagged "
    return xml_tag_contents(xml, 'SUMMARY_BODY')

def rm_quality(xml):
    " retrieves the clinical implications, returns html tagged"
    return xml_tag_contents(xml, 'QUALITY_OF_EVIDENCE')


def rm_outcomes(xml):
    " retrieves the clinical implications, returns html tagged"
    return xml_tag_contents(xml, 'CRIT_OUTCOMES')


def rm_searchdate(xml):
    " retrives the search date, parses and returns string "
    last_search = xml.getElementsByTagName('LAST_SEARCH')
    date = last_search[0].getElementsByTagName('DATE')
    year = date[0].attributes['YEAR'].value
    # sketched in code to retrieve month
    month = date[0].attributes['MONTH'].value

    return "%s %s" % (MONTH_NAMES[int(month)-1], year)



def rm_narrative(octype, intname, cntname, name, units, point, ci95low, ci95up, studies, participants, show_participants):
    " returns a Clinical Evidence style sentence from all this data "
    if units[-1] == "R" or units.upper()[-10:] == "RATE RATIO":
        cutoff = 1
    else:
        cutoff = 0

    intname = mid_sent(intname)
    cntname = mid_sent(cntname)
    name = mid_sent(name)

    if show_participants:
        participants_str = "with %s participants" % (participants,)
    else:
        participants_str = "(number of participants not available)"



    if (Decimal(ci95low) == 0) and (Decimal(point) == 0) and (Decimal(ci95up) == 0):
        nresult = "ERROR - no narrative result possible since effect size and 95% CI set to 0."
        # ERROR_LOG.append("Narrative result error - please see below")
        # print "NR ERROR"
    elif (Decimal(ci95low) < cutoff) and (Decimal(ci95up) > cutoff):
        nresult = "%s %s found no statistically significant difference between groups." % (start_sent(numberword("RCT", int(studies))), participants_str)
    elif (Decimal(ci95low) < cutoff) and (Decimal(ci95up) < cutoff):
        nresult = "%s %s found that fewer people had %s with %s than with %s." % (start_sent(numberword("RCT", int(studies))), participants_str, name, intname , cntname)
    elif (Decimal(ci95low) > cutoff) and (Decimal(ci95up) > cutoff):
        nresult = "%s %s found that more people had %s with %s than with %s." % (start_sent(numberword("RCT", int(studies))), participants_str, name, intname, cntname)
    else:
        print "ERROR - unexpected XML contents in this review"
    return nresult


def rm_picos(xml):
    """
    MAIN LOOP

    takes in xml at comparison level
    parses and returns as HTML

    """

    picolist = []
    comparisons = xml.getElementsByTagName('COMPARISON')
    cdno =  rm_unique(xml)
    searchdate = rm_searchdate(xml)

    for c in range(len(comparisons)):
        titlexml = comparisons[c].getElementsByTagName('NAME')
        title = titlexml[0].firstChild.data # comparison title

        c_no = xml_attribute_contents(comparisons[c], "NO") # comparison index


        picolist.append(tabtag(tag("Comparison ", "h3"), tag(title, "h3")))

        picolist.append(tabtag("Population", " "))
        picolist.append(tabtag("Intervention", " "))
        picolist.append(tabtag("Comparator", " "))
        picolist.append(tabtag("Safety alerts", " "))

        outcomes=[i for i in comparisons[c].childNodes if i.nodeName in ["DICH_OUTCOME", "CONT_OUTCOME", "IV_OUTCOME", "IPD_OUTCOME"]]

        for o in range(len(outcomes)):
            intxml = outcomes[o].getElementsByTagName('GROUP_LABEL_1')
            if len(intxml) > 0:
                try:
                    intname = intxml[0].firstChild.data
                except:
                    picolist.append(tabtag(tag(("Comparison skipped from Revman file here"), "h3")))
                    picolist.append(tabtag(("In tests, this was due to errors in the original file where the authors have incompletely filled in the intervention field.")))
                    continue

            else:
                intname = "NO INTERVENTION FOUND"
            try:
                cntxml = outcomes[o].getElementsByTagName('GROUP_LABEL_2')
            except:
                picolist.append(tabtag(tag(("Comparison skipped from Revman file here"), "h3")))
                picolist.append(tabtag(("In tests, this was due to errors in the original file where the authors have incompletely filled in the control field.")))


            if len(cntxml) > 0:
                cntname = cntxml[0].firstChild.data
            else:
                intname = "NO CONTROL FOUND"

            participants_shown_attr = outcomes[o].attributes.get("SHOW_PARTICIPANTS")
            if participants_shown_attr and participants_shown_attr.value == "NO":
                show_participants = False
            else:
                show_participants = True

            data = ocparse(outcomes[o])

            o_no = xml_attribute_contents(outcomes[o], "NO")

            (octype, name, units, point, ci95low, ci95up, favours1, favours2, studies, participants, usetotal, subgroupspresent, study_text) = data
            ocstr = "%s.%s" % (c_no, o_no)
            octitle = ("Outcome %s" % (ocstr, ))


            picolist += rm_dataparse(title, octitle, octype, name, intname, cntname, units, point, ci95low, ci95up, favours1, favours2, studies, participants, show_participants, usetotal, outcomes[o], cdno, ocstr, searchdate, study_text)

            if subgroupspresent == "YES":
                subgroups = outcomes[o].getElementsByTagName('DICH_SUBGROUP') + outcomes[o].getElementsByTagName('CONT_SUBGROUP') + outcomes[o].getElementsByTagName('IV_SUBGROUP') + outcomes[o].getElementsByTagName('IPD_SUBGROUP')


                for s in range(len(subgroups)):

                    participants_shown_attr = outcomes[o].attributes.get("SHOW_PARTICIPANTS")
                    if participants_shown_attr and participants_shown_attr.value == "NO":
                        show_participants = False
                    else:
                        show_participants = True

                    s_no = xml_attribute_contents(subgroups[s], "NO")

                    data = ocparse(subgroups[s], checkfav = False) #want to use the existing favours string
                    (octype, sgname, dummy0, point, ci95low, ci95up, dummy1, dummy2, studies, participants, usetotal, dummy3, study_text) = data #slight hack, assigning favours to dummystring, subgroups, and units
                    ocstr = "%s.%s.%s" % (c_no, o_no, s_no)
                    octitle = ("Subgroup analysis %s" % (ocstr,))
                    picolist += rm_dataparse(title, octitle, octype, name, intname, cntname, units, point, ci95low, ci95up, favours1, favours2, studies, participants, show_participants, usetotal, subgroups[s], cdno, ocstr, searchdate, study_text, sgname)
    return picolist


def rm_dataparse(title, octitle, octype, name, intname, cntname, units, point, ci95low, ci95up, favours1, favours2, studies, participants, show_participants, usetotal, xml, cdno, ocstr, searchdate, study_text, sgname = None):
    """
    take statistical data
    parse, and output as CCA text
    """

    if sgname:
        # indicate whether this is a subgroup
        sgname = name + " - [subgroup: " + sgname + "]"
    else:
        sgname = name

    picolist = []
    picolist.append(tabtag(tag(octitle, "h4"), tag(sgname, "h4")))

    if usetotal == "SUB":
        # no overall meta-analysis; subgroups only will be reported in CCA (as in original review)
        picolist.append(tabtag(tag("Analysed by subgroup only", "h4")))

    else:
        # yes - there is an overall meta-analysis
        if studies == "0":
            nresult = "We found no studies meeting our criteria which assessed the effect of " + mid_sent(title) + " on " + mid_sent(name)
            qresult = "n/a"
            abresult = "n/a"
        elif type(point) == type(None):
            nresult = "No narrative result is available for this analysis. (The analysis includes multiple studies but no meta-analysis was conducted.)"
            qresult = "The results from individual studies were: " + study_text + "; Forest plot details: " + cdno + " Analysis " + ocstr
            abresult = "The absolute effect in each group cannot be calculated as data were not meta-analysed."
        else:
            nresult = rm_narrative(octype, intname, cntname, name, units, point, ci95low, ci95up, studies, participants, show_participants)
            if xml.nodeName == "IV_OUTCOME" or xml.nodeName == "IV_SUBGROUP":
                abresult = "The absolute effect in each group cannot be calculated using only the generic inverse variance data from this analysis."
           # elif xml.nodeName == "IPD_OUTCOME" or xml.nodeName == "IPD_SUBGROUP":
           #     abresult = "The absolute effect in each group cannot be calculated from time-to-event data (hazard ratios)."
            elif xml.nodeName == "CONT_OUTCOME" or xml.nodeName == "CONT_SUBGROUP": # new insertion - no longer want continuous o/cs calculated
                abresult = " "
            elif units[-2:] == "OR" or units[-2:] == "RR" or units.upper()[-10:] == "RATE RATIO":
                abresult = rm_abs_values(octype, intname, cntname, name, units, point, ci95low, ci95up, studies, participants, xml)
            else:
                abresult = "The absolute effect in each group cannot be calculated using " + units + " from this analysis"


            if units[-1] == "R" or units.upper()[-10:] == "RATE RATIO":
                cutoff = 1
            else:
                cutoff = 0

            if ci95up < cutoff:
                favours = "There was a statistically significant difference between groups, " + favours_parser(favours1)
            elif ci95low > cutoff:
                favours = "There was a statistically significant difference between groups, " + favours_parser(favours2)
            else:
                favours = "There was no statistically significant difference between groups"

            qresult = favours + " (" + units + " " + str(point.quantize(Decimal('.01'))) + ", 95% CI " + str(ci95low.quantize(Decimal('.01'))) + " to " + str(ci95up.quantize(Decimal('.01'))) + "). Forest plot details: " + cdno + " Analysis " + ocstr

        picolist.append(tabtag("Narrative result", nresult))
        picolist.append(tabtag("Risk of bias of studies", "The reviewers did not perform a GRADE assessment of the quality of the evidence. Of the X studies, X (%) failed to report adequate allocation concealment and/or random sequence generation, X (%) did not report adequate blinding of participants/carers/outcome assessors and X (%) had high or unclear numbers of withdrawals."))
        picolist.append(tabtag("Quality of the evidence", "The reviewers performed a GRADE assessment of the quality of evidence for this outcome at this time point and stated that the evidence was [] quality. See Summary of findings from Cochrane review"))
        picolist.append(tabtag("Quantitative result: relative effect or mean difference", qresult))

        picolist.append(tabtag("Quantitative result: absolute effect", abresult))
        picolist.append(tabtag("Reference", cdno))
        picolist.append(tabtag("Search date", searchdate))
    return picolist







#
# data validation functions
#

def val_comparison(txt):
    """
    check comparisons, return true or false
    check 1 - does it have v, versus, or vs?
    """
    vcheck = False

    for v in [" v ", " v. ", " vs ", " vs. ", " versus "]:
        if v in txt:
            vcheck = True

    if not vcheck:
        ERROR_LOG.append("Outcome name without intervention and control")
    return vcheck

#
#   output functions
#

def outputfile(inputfile):
    """
    returns output filename from input filename (same name with txt extension moved to op directory)
    """

    return os.path.join(PATH["op"], os.path.splitext(os.path.split(inputfile)[-1])[0]+".doc")

def htmlfile(inputfile):
    """
    returns output filename from input filename (same name with txt extension moved to op directory)
    """
    return os.path.join(PATH["op"], os.path.splitext(os.path.split(inputfile)[-1])[0]+".html")



def datecode():
    """
    top of file date/time/compiler options stamp
    """
    if DISPLAY_COMMENTS:
        ccom_s = "ON"
    else:
        ccom_s = "OFF"
    d = datetime.now()
    d_s = d.strftime('%d-%m-%y - %H:%M:%S')
    return "PICO generator v" + PICOTRON_VERSION + "; text complied @ " + d_s + "; compiler comments " + ccom_s

def tag(contents, tag, cls = ""):
    """
    returns content html tagged, and indented 2x tabs (for ease of reading output)
    """
    if cls is not "":
        cls = ' class="' + cls + '"'
    return "\t\t<" + tag + cls + ">" + contents + "</" + tag + ">"

def tabtag(x, y = "", celltag = "td"):
    """
    returns a one or two headed table row, with option to make different tag (i.e. th)
    """

    if y == "":
        colspan = ' colspan = 2'
    else:
        colspan = ''
        y = "<" + celltag + ">" + y + "</" + celltag + ">"
    x = "<" + celltag + colspan + " class='leftcol'>" + x + "</" + celltag + ">"
    return "\t\t\t<tr>" + x + y + "</tr>"

def writefile(filename, txt):
    """
    write output as unicode
    """
    op = codecs.open(filename, 'wb', 'utf-8')
    op.write(txt)
    op.close()




def main():
    files = glob.glob(os.path.join(PATH["rev"],  "*.rm5")) # get all reviews
    topic_lookup = parse_topics(get_topic_filename())
    os.system("clear")
    print INTRO

    nofiles = len(files)
    nofiles_u = len(set(files))
    print "%d files found - processing..." % (nofiles,)
    print "(%d unique files)" % (nofiles_u,)

    files_count = collections.Counter(files)
    duplicates = [i for i in files_count if files_count[i]>1]
    if duplicates:
        print "The following duplicates were found ", ",".join(duplicates)

    not_done = []

    p = progressbar.ProgressBar(nofiles, timer=True)

    for c in range(nofiles):
        p.tap()

        try:

            f = files[c]

            op = []
            xmldoc = minidom.parse(f)

            if not rm_is_intervention_review(xmldoc): # only process intervention style reviews for the purposes of CCA
                continue # = skip

            op.append(HTML_HEADER)
            op.append(tag("Cochrane Clinical Answers", "h3"))



            q = rm_title(xmldoc)

            (intname, cntname, cndname, popname, patternno) = splitter(mid_sent(q))
            if intname:
                qu = randomquestion(intname, cntname, cndname, popname, patternno)
            else:
                qu = "[Sorry, it was not possible to auto-generate a question (the wording of the review title was not in the expected format).]"

            op.append(tag(qu, "h1"))


            op.append(TABLE_HEADER)

            cdno =  rm_unique(xmldoc)

            op.append(tabtag(tag("Notes to Associate Editor from Cochrane Review " + cdno + " [not for publication]", "h3")))
            # print cdno

            topic_headers = "; ".join(list(topic_lookup[cdno]))


            op.append(tabtag("Review title", q))

            # op.append(tabtag("Short conclusions<br/>(Abstract > Conclusions)", rm_summaryshort(xmldoc)))
            # op.append(tabtag("Long conclusions<br/>(Authors' conclusions > Implications for practice)", rm_implications(xmldoc)))

            # op.append(tabtag("Population<br/>(Methods > Criteria for considering studies for this review > Types of participants)", rm_overview_p(xmldoc)))
            # op.append(tabtag("Interventions<br/>(Methods > Criteria for considering studies for this review > Types of interventions)", rm_overview_i(xmldoc)))
            op.append(tabtag("Outcomes<br/>(Methods > Criteria for considering studies for this review > Types of outcome measures)", rm_outcomes(xmldoc)))
            # op.append(tabtag("Risk of bias of studies<br/>(Results > Risk of bias in included studies)", rm_quality(xmldoc)))
            op.append(TABLE_FOOTER)


            op.append(tag(" ", "br"))

            op.append(TABLE_HEADER)
            op.append(tabtag(tag("CCA number", "h4"), "cca "))
            op.append(tabtag(tag("DOI", "h4"), "10.1002/cca."))
            op.append(TABLE_FOOTER)

            op.append(tag(" ", "br"))


            op.append(TABLE_HEADER)
            op.append(tabtag(tag("Clinical question", "h4"), qu))
            op.append(tabtag("Clinical answer", " "))
            op.append(tabtag("Abstract", "This Cochrane Clinical Answer evaluates %s in people with %s." % (intname, cndname)))

            # no longer needed
            # op.append(tabtag("Keywords", " "))

            op.append(tabtag("Subject (1)", topic_headers))
            op.append(tabtag("Subject (2)", " "))
            op.append(tabtag("Subject (3)", " "))

            # no longer needed
            # op.append(tabtag("MeSH codes", " "))

            op.append(TABLE_FOOTER)


            op.append(tag(" ", "br"))

            op.append(tag(datecode(), "p", "compiler"))
            op.append("!/!/!/!/COMPILER!/!/!/!/")


            op.append(TABLE_HEADER)
            op.append(tabtag(tag("PICOS", "h3")))
            op += rm_picos(xmldoc)
            op.append(TABLE_FOOTER)


            op.append(HTML_FOOTER)


            # add in error log if compiler comments = True
            ccom_index = op.index("!/!/!/!/COMPILER!/!/!/!/")

            if DISPLAY_COMMENTS:
                for e in range(len(ERROR_LOG)):
                    ERROR_LOG[e] = tag(ERROR_LOG[e], "p", "compiler")
                op = op[:ccom_index] + ERROR_LOG + op [ccom_index + 1:]
            else:
                op[ccom_index] = ""

            writefile(outputfile(f), '\n'.join(op))

        except:
            print "error, file %s not done" % (files[c], )
            not_done.append(files[c])


    if not_done:
        with open('not_done.txt', 'wb') as not_done_f:
            not_done_f.write("The following files were not able to be processed due to errors:\n\n")
            not_done_f.write("\n".join(not_done))
    print ""
    print "done!"
    


if __name__ == "__main__":
    main()
