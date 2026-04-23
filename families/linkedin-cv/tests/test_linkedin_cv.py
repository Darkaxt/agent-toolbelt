import json
import os
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "packages" / "core" / "src"
FAMILY_SRC = REPO_ROOT / "families" / "linkedin-cv" / "src"
for path in (CORE_SRC, FAMILY_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agent_toolbelt_linkedin_cv import linkedin_cv  # noqa: E402


PUBLIC_PROFILE_HTML = """
<html>
  <body>
    <main>
      <section class="top-card-layout">
        <h1>Jane Candidate</h1>
        <h2>Senior Detection Engineer helping SaaS teams reduce alert fatigue</h2>
        <span class="top-card__subline-item">Berlin, Germany</span>
      </section>
      <section>
        <h2>About</h2>
        <div>Builds threat detection programs with measurable incident outcomes.</div>
      </section>
      <section>
        <h2>Experience</h2>
        <ul>
          <li>Lead Security Engineer at ExampleCo</li>
          <li>Security Engineer at PreviousCo</li>
        </ul>
      </section>
      <section>
        <h2>Education</h2>
        <div>MSc Computer Science</div>
      </section>
      <section>
        <h2>Skills</h2>
        <span>Detection Engineering</span>
        <span>Python</span>
      </section>
    </main>
  </body>
</html>
"""


OWN_PROFILE_HTML = """
<html>
  <body>
    <main>
      <section>
        <h1>Alex Candidate</h1>
        <div class="text-body-medium break-words">Security engineer</div>
      </section>
      <section><h2>Experience</h2><div>Engineer at OwnCo</div></section>
    </main>
  </body>
</html>
"""


OWN_PROFILE_RICH_HTML = """
<html>
  <head><title>Alex Candidate | LinkedIn</title></head>
  <body>
    <div class="profile-shell">
      <h2>0 notifications</h2>
      <a href="https://www.linkedin.com/in/alex-candidate/" aria-label="Alex Candidate">
        <div>
          <p>Alex Candidate</p>
          <div>
            <p>Senior Detection Engineer | Security Automation | Incident Response</p>
          </div>
        </div>
      </a>
      <p>ExampleCo · Example University</p>
      <p>Berlin, Germany</p>
    </div>
  </body>
</html>
"""


THIN_OWN_PROFILE_HTML = """
<html>
  <body>
    <main>
      <section>
        <h1>Alex Candidate</h1>
        <div>Security engineer</div>
        <p>Berlin, Germany</p>
      </section>
      <section>
        <h2>About</h2>
        <div>Security engineer.</div>
      </section>
      <section>
        <h2>Experience</h2>
        <ul>
          <li>Engineer at OwnCo</li>
        </ul>
      </section>
    </main>
  </body>
</html>
"""


ABOUT_EXPANDABLE_HTML = """
<html>
  <body>
    <main>
      <section>
        <h1>Alex Candidate</h1>
        <div>Senior Detection Engineer</div>
        <p>Berlin, Germany</p>
      </section>
      <div class="_01df4767 _80e7aa20 bb00e126 _87746ce5 _72087b5b _46240ce1 _0dd04db4">
        <div class="_01df4767 _80e7aa20 bb00e126 _87746ce5 _72087b5b _46240ce1 _0dd04db4">
          <div class="eb67b983 _74112791 _1938e3bc _898c56f6 _80e7aa20 b7c84f46 _4184c746 _9462823e _46240ce1 _0dd04db4">
            <h2>About</h2>
            <div>
              <a
                aria-disabled="false"
                href="https://www.linkedin.com/in/alex-candidate/edit/forms/summary/new/"
                aria-label="Edit about"
              >Edit</a>
            </div>
          </div>
          <div class="_01df4767 _84e0571d _1938e3bc _0160a0de _80e7aa20 bb00e126 _87746ce5 _72087b5b _46240ce1 _0dd04db4">
            <p>
              <span tabindex="-1" data-testid="expandable-text-box">
                With over a decade in cybersecurity, I focus on identifying operational pain points and engineering the automation that eliminates them.
                <button aria-hidden="true" data-testid="expandable-text-button">
                  <span><span>…</span><span> more</span></span>
                </button>
              </span>
            </p>
            <div>
              <p>Top skills</p>
              <p>Security Operations • Incident Response • Security Automation</p>
            </div>
          </div>
        </div>
      </div>
    </main>
  </body>
</html>
"""


DETAIL_EXPERIENCE_HTML = """
<html>
  <body>
    <main>
      <section>
        <h1>Alex Candidate</h1>
      </section>
      <section>
        <h2>Experience</h2>
        <ul>
          <li>Senior Security Engineer at ExampleCo</li>
          <li>Incident Response Lead at PreviousCo</li>
        </ul>
      </section>
      <section>
        <h2>Skills</h2>
        <ul>
          <li>SIEM</li>
          <li>SOAR</li>
        </ul>
      </section>
    </main>
  </body>
</html>
"""


ROUTE_STYLE_EXPERIENCE_HTML = """
<html>
  <body>
    <main>
      <div>Experience</div>
      <a href="https://www.linkedin.com/in/alex-candidate/details/experience/edit/forms/1/">
        Senior Security Engineer\n\n2023 - Present
      </a>
      <a href="https://www.linkedin.com/in/alex-candidate/details/experience/edit/forms/2/">
        Incident Response Lead\n\n2021 - 2023
      </a>
      <div>About</div>
    </main>
  </body>
</html>
"""


ROUTE_STYLE_LANGUAGES_HTML = """
<html>
  <body>
    <main>
      <div>Languages</div>
      <div>English</div>
      <div>Full professional proficiency</div>
      <div>Spanish</div>
      <div>Native or bilingual proficiency</div>
      <div>About</div>
    </main>
  </body>
</html>
"""


DEEP_MAIN_PROFILE_HTML = """
<html>
  <body>
    <main>
      <section>
        <h1>Alex Candidate</h1>
        <div>Security engineer</div>
        <p>Berlin, Germany</p>
      </section>
      <section>
        <h2>About</h2>
        <div>Security engineer.</div>
        <a href="https://www.linkedin.com/in/alex-candidate/details/experience/">Show all experiences</a>
      </section>
      <section>
        <h2>Experience</h2>
        <ul>
          <li>Engineer at OwnCo</li>
        </ul>
      </section>
    </main>
  </body>
</html>
"""


CANONICAL_OWN_PROFILE_HTML = """
<html>
  <head><title>Alex Candidate | LinkedIn</title></head>
  <body>
    <main>
      <section>
        <h1>Alex Candidate</h1>
        <div>Security engineer</div>
        <p>Berlin, Germany</p>
      </section>
      <section>
        <h2>About</h2>
        <div>Security engineer.</div>
      </section>
    </main>
  </body>
</html>
"""


NESTED_RICH_SECTION_HTML = """
<html>
  <body>
    <main>
      <section>
        <h1>Alex Candidate</h1>
        <div>Security engineer</div>
        <p>Berlin, Germany</p>
      </section>
      <section>
        <div>
          <h2>Experience</h2>
          <div>Lead Security Engineer at ExampleCo</div>
          <div>
            <h2>Experience</h2>
          </div>
        </div>
      </section>
    </main>
  </body>
</html>
"""


SKILLS_COUNT_MAIN_PROFILE_HTML = """
<html>
  <head><title>Alex Candidate | LinkedIn</title></head>
  <body>
    <main>
      <section>
        <h1>Alex Candidate</h1>
        <div>Security engineer</div>
        <p>Berlin, Germany</p>
      </section>
      <section>
        <h2>Skills (25)</h2>
        <a href="https://www.linkedin.com/in/alex-candidate/details/skills/">Show all</a>
      </section>
    </main>
  </body>
</html>
"""


EMPTY_SKILLS_DETAIL_HTML = """
<html>
  <body>
    <main>
      <div>Skills</div>
    </main>
  </body>
</html>
"""


SKILLS_RSC_RESPONSE_TEXT = r"""
0:[["$","$L1",null,{"modelStates":[],"isPartialPage":true}],"skill-page",[
["{\"key\":\"skill-20\"}",["$","div",null,{"componentKey":"com.linkedin.sdui.profile.skill(ACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbco, 20)","children":[["$","$L5",null,{"textProps":{"fontFamily":"sans","fontSize":"medium","fontStyle":"normal","fontWeight":"bold","children":["Software Architecture"]}}],["$","$L5",null,{"textProps":{"fontWeight":"normal","children":["RedCurve — Local-First Endpoint Investigation Platform"]}}],["$","$L7",null,{"buttonProps":{"aria-label":"Edit Software Architecture skill"}}]]}]],
["{\"key\":\"skill-21\"}",["$","div",null,{"componentKey":"com.linkedin.sdui.profile.skill(ACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbco, 21)","children":[["$","$L5",null,{"textProps":{"fontFamily":"sans","fontSize":"medium","fontStyle":"normal","fontWeight":"bold","children":["Systems Programming"]}}],["$","$L7",null,{"buttonProps":{"aria-label":"Edit Systems Programming skill"}}]]}]],
["{\"key\":\"skill-22\"}",["$","div",null,{"componentKey":"com.linkedin.sdui.profile.skill(ACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbco, 22)","children":[["$","$L5",null,{"textProps":{"fontFamily":"sans","fontSize":"medium","fontStyle":"normal","fontWeight":"bold","children":["Rust (Programming Language)"]}}],["$","$L7",null,{"buttonProps":{"aria-label":"Edit Rust (Programming Language) skill"}}]]}]],
["{\"key\":\"skill-23\"}",["$","div",null,{"componentKey":"com.linkedin.sdui.profile.skill(ACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbco, 23)","children":[["$","$L5",null,{"textProps":{"fontFamily":"sans","fontSize":"medium","fontStyle":"normal","fontWeight":"bold","children":["Event Tracing for Windows (ETW)"]}}],["$","$L7",null,{"buttonProps":{"aria-label":"Edit Event Tracing for Windows (ETW) skill"}}]]}]],
["{\"key\":\"skill-24\"}",["$","div",null,{"componentKey":"com.linkedin.sdui.profile.skill(ACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbco, 24)","children":[["$","$L5",null,{"textProps":{"fontWeight":"normal","children":["RedCurve — Local-First Endpoint Investigation Platform"]}}],["$","$L7",null,{"buttonProps":{"aria-label":"Edit SIGMA Rules skill"}}]]}]]
]]
"""


UNRELATED_RSC_RESPONSE_TEXT = r"""
0:[["$","$L1",null,{"modelStates":[],"isPartialPage":true}],"languages-page",[
["{\"key\":\"lang-1\"}",["$","div",null,{"componentKey":"com.linkedin.sdui.profile.language(ACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbco, 1)","children":[["$","$L5",null,{"textProps":{"fontWeight":"bold","children":["English"]}}]]}]]
]]
"""


def make_skills_rsc_response_text(skills: list[str], *, next_start: int | None = None) -> str:
    blocks = []
    for offset, skill in enumerate(skills, start=1):
        block = (
            f'[\"{{\\\"key\\\":\\\"skill-{offset}\\\"}}\",'
            f'[\"$\",\"div\",null,{{\"componentKey\":\"com.linkedin.sdui.profile.skill(ACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbco, {offset})\",'
            f'\"children\":[[\"$\",\"$L5\",null,{{\"textProps\":{{\"fontFamily\":\"sans\",\"fontSize\":\"medium\",\"fontStyle\":\"normal\",\"fontWeight\":\"bold\",\"children\":[\"{skill}\"]}}}}],'
            f'[\"$\",\"$L7\",null,{{\"buttonProps\":{{\"aria-label\":\"Edit {skill} skill\"}}}}]]}}]]'
        )
        blocks.append(block)
    response = '0:[[\"$\",\"$L1\",null,{\"modelStates\":[],\"isPartialPage\":true}]'
    if next_start is not None:
        pagination_request = {
            "$type": "proto.sdui.actions.requests.PaginationRequest",
            "pagerId": "com.linkedin.sdui.pagers.profile.details.skills",
            "requestedArguments": {
                "$type": "proto.sdui.actions.requests.RequestedArguments",
                "payload": {
                    "start": next_start,
                    "count": 10,
                    "vanityName": "alex-candidate",
                    "profileId": "ACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbco",
                },
                "requestedStateKeys": [],
                "requestMetadata": {"$type": "proto.sdui.common.RequestMetadata"},
            },
            "trigger": {
                "$case": "itemDistanceTrigger",
                "itemDistanceTrigger": {
                    "$type": "proto.sdui.actions.requests.ItemDistanceTrigger",
                    "preloadDistance": 3,
                    "preloadLength": 250,
                },
            },
            "retryCount": 2,
        }
        response += "," + json.dumps(json.dumps(pagination_request), ensure_ascii=False)
    response += ',\"skill-page\",[' + ",".join(blocks) + "]]"
    return response


def build_skills_pagination_request(start: int, *, count: int = 10) -> dict:
    return {
        "$type": "proto.sdui.actions.requests.PaginationRequest",
        "pagerId": "com.linkedin.sdui.pagers.profile.details.skills",
        "requestedArguments": {
            "$type": "proto.sdui.actions.requests.RequestedArguments",
            "payload": {
                "start": start,
                "count": count,
                "vanityName": "alex-candidate",
                "profileId": "ACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbco",
                "filter": "ProfileSkillCategory_ALL",
            },
            "requestedStateKeys": [],
            "requestMetadata": {"$type": "proto.sdui.common.RequestMetadata"},
        },
        "trigger": {
            "$case": "itemDistanceTrigger",
            "itemDistanceTrigger": {
                "$type": "proto.sdui.actions.requests.ItemDistanceTrigger",
                "preloadDistance": 3,
                "preloadLength": 250,
            },
        },
        "retryCount": 2,
    }


SKILLS_COMO_REHYDRATION = {
    "$LskillsPager": {
        "observabilityIdentifier": "com.linkedin.sdui.pagers.profile.details.skills",
        "children": "$L7c",
    },
    "$L7c": {"children": "$La7"},
    "$La7": {"children": "$Lbe"},
    "$Lbe": {"nextPageRequest": build_skills_pagination_request(0)},
}


SKILLS_COMO_HTML = f"""
<html>
  <body>
    <script>
      window.__como_rehydration__ = {json.dumps(SKILLS_COMO_REHYDRATION, ensure_ascii=False)};
    </script>
  </body>
</html>
"""


LANGUAGES_ROUTE_MAIN_PROFILE_HTML = """
<html>
  <head><title>Alex Candidate | LinkedIn</title></head>
  <body>
    <main>
      <section>
        <h1>Alex Candidate</h1>
        <div>Security engineer</div>
        <p>Berlin, Germany</p>
      </section>
      <section>
        <h2>Languages</h2>
        <a href="https://www.linkedin.com/in/alex-candidate/details/languages/">Show all</a>
      </section>
    </main>
  </body>
</html>
"""


def build_languages_pagination_request(start: int, *, count: int = 10) -> dict:
    return {
        "$type": "proto.sdui.actions.requests.PaginationRequest",
        "pagerId": "com.linkedin.sdui.pagers.profile.details.languages",
        "requestedArguments": {
            "$type": "proto.sdui.actions.requests.RequestedArguments",
            "payload": {
                "start": start,
                "count": count,
                "vanityName": "alex-candidate",
                "profileId": "ACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbco",
            },
            "requestedStateKeys": [],
            "requestMetadata": {"$type": "proto.sdui.common.RequestMetadata"},
        },
        "trigger": {
            "$case": "itemDistanceTrigger",
            "itemDistanceTrigger": {
                "$type": "proto.sdui.actions.requests.ItemDistanceTrigger",
                "preloadDistance": 3,
                "preloadLength": 250,
            },
        },
        "retryCount": 2,
    }


LANGUAGES_COMO_HTML = f"""
<html>
  <body>
    <script>
      window.__como_rehydration__ = {json.dumps(
          [
              '41:["$","$L3f",null,{{"observabilityIdentifier":"com.linkedin.sdui.pagers.profile.details.languages","children":["$","$L36",null,{{"componentKey":"com.linkedin.sdui.profile.card.refACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbcoLanguageDetails","children":"$L6f"}}]}}]',
              '6f:["$","div",null,{{"data-testid":"lazy-column","data-component-type":"LazyColumn","children":["$undefined","$L94","$undefined","$undefined"]}}]',
              '94:["$","$La4",null,{{"children":["$","$L33",null,{{"paginationNeeded":true,"children":"$La5"}}]}}]',
              f'a5:["$","$Lc7",null,{{"nextPageRequest":{json.dumps(build_languages_pagination_request(0), ensure_ascii=False)}}}]',
          ],
          ensure_ascii=False,
      )};
    </script>
  </body>
</html>
"""


def make_languages_rsc_response_text(entries: list[tuple[str, str]]) -> str:
    blocks = []
    for index, (language, proficiency) in enumerate(entries, start=1):
        blocks.append(
            '[["{\\"key\\":\\"language-%d\\"}",["$","div",null,{"children":[["$","p",null,{"children":["%s"]}],["$","p",null,{"children":["%s"]}]]}]],'
            '["$","div",null,{"children":["$","$L6",null,{"viewTrackingSpecs":{"viewName":"languages-edit-button","legacyControlName":"edit_languages"},'
            '"children":["$","$L3",null,{"buttonProps":{"aria-label":"Edit language"}}]}]}]]'
            % (index, language, proficiency)
        )
    return '0:[["$","$L1",null,{"modelStates":[],"isPartialPage":true}],"$undefined",[%s]]' % ",".join(blocks)


def build_education_pagination_request(start: int, *, count: int = 10) -> dict:
    return {
        "$type": "proto.sdui.actions.requests.PaginationRequest",
        "pagerId": "com.linkedin.sdui.pagers.profile.details.education",
        "requestedArguments": {
            "$type": "proto.sdui.actions.requests.RequestedArguments",
            "payload": {
                "start": start,
                "count": count,
                "vanityName": "alex-candidate",
                "profileId": "ACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbco",
                "detailSectionReplaceableComponentRef": "$L6f",
            },
            "requestedStateKeys": [],
            "requestMetadata": {"$type": "proto.sdui.common.RequestMetadata"},
        },
        "trigger": {
            "$case": "itemDistanceTrigger",
            "itemDistanceTrigger": {
                "$type": "proto.sdui.actions.requests.ItemDistanceTrigger",
                "preloadDistance": 3,
                "preloadLength": 250,
            },
        },
        "retryCount": 2,
    }


EDUCATION_COMO_HTML = f"""
<html>
  <body>
    <script>
      window.__como_rehydration__ = {json.dumps(
          [
              '41:["$","$L3f",null,{{"observabilityIdentifier":"com.linkedin.sdui.pagers.profile.details.education","children":["$","$L36",null,{{"componentKey":"com.linkedin.sdui.profile.card.refACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbcoEducationDetails","children":"$L6f"}}]}}]',
              '6f:["$","div",null,{{"data-testid":"lazy-column","data-component-type":"LazyColumn","children":["$undefined","$L94","$undefined","$undefined"]}}]',
              '94:["$","$La4",null,{{"children":["$","$L33",null,{{"paginationNeeded":true,"children":"$La5"}}]}}]',
              f'a5:["$","$Lc7",null,{{"nextPageRequest":{json.dumps(build_education_pagination_request(0), ensure_ascii=False)}}}]',
          ],
          ensure_ascii=False,
      )};
    </script>
  </body>
</html>
"""


def make_education_rsc_response_text(records: list[dict[str, object]], *, next_start: int | None = None) -> str:
    blocks = []
    for index, record in enumerate(records, start=1):
        school = str(record["school"])
        school_url = str(record.get("school_url", ""))
        degree = str(record.get("degree", ""))
        field_of_study = str(record.get("field_of_study", ""))
        date_range = str(record.get("date_range", ""))
        edit_form_id = int(record.get("edit_form_id", index))
        raw_lines = [str(item) for item in record.get("raw_lines", [])]
        degree_line = degree
        if field_of_study:
            degree_line = f"{degree}, {field_of_study}" if degree else field_of_study
        parts = []
        if school_url:
            parts.append(f'["$","a",null,{{"href":"{school_url}"}}]')
        parts.append(f'["$","a",null,{{"href":"https://www.linkedin.com/in/alex-candidate/details/education/edit/forms/{edit_form_id}/"}}]')
        parts.append(f'["$","p",null,{{"children":["{school}"]}}]')
        if degree_line:
            parts.append(f'["$","p",null,{{"children":["{degree_line}"]}}]')
        if date_range:
            parts.append(f'["$","p",null,{{"children":["{date_range}"]}}]')
        for raw_line in raw_lines:
            parts.append(f'["$","p",null,{{"children":["{raw_line}"]}}]')
        blocks.append(
            f'[\"{{\\\"key\\\":\\\"education-{index}\\\"}}\",[\"$\",\"div\",null,{{\"componentKey\":\"com.linkedin.sdui.profile.education(ACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbco, {index})\",\"children\":[{",".join(parts)}]}}]]'
        )
    response = '0:[[\"$\",\"$L1\",null,{\"modelStates\":[],\"isPartialPage\":true}]'
    if next_start is not None:
        response += "," + json.dumps(json.dumps(build_education_pagination_request(next_start)), ensure_ascii=False)
    response += ',\"education-page\",[' + ",".join(blocks) + "]]"
    return response


def make_education_edit_form_html(
    *,
    school: str,
    degree: str,
    field_of_study: str,
    start_year: int,
    end_year: int,
    description: str = "",
    activities: str = "",
    grade: str = "",
) -> str:
    description_ref = "$f" if description else ""
    activities_ref = "$10" if activities else ""
    states = [
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "education.dataAwareAddEducationFormComponentschoolName",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "education.dataAwareAddEducationFormComponentschoolName"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "stringValue", "stringValue": school},
            "persistence": None,
            "isOptimistic": False,
        },
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "education.dataAwareAddEducationFormComponentdegree",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "education.dataAwareAddEducationFormComponentdegree"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "stringValue", "stringValue": degree},
            "persistence": None,
            "isOptimistic": False,
        },
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "education.dataAwareAddEducationFormComponentfieldOfStudy",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "education.dataAwareAddEducationFormComponentfieldOfStudy"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "stringValue", "stringValue": field_of_study},
            "persistence": None,
            "isOptimistic": False,
        },
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "education.dataAwareAddEducationFormComponentdescription",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "education.dataAwareAddEducationFormComponentdescription"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "stringValue", "stringValue": description_ref},
            "persistence": None,
            "isOptimistic": False,
        },
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "education.dataAwareAddEducationFormComponentactivities",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "education.dataAwareAddEducationFormComponentactivities"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "stringValue", "stringValue": activities_ref},
            "persistence": None,
            "isOptimistic": False,
        },
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "education.dataAwareAddEducationFormComponentgrade",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "education.dataAwareAddEducationFormComponentgrade"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "stringValue", "stringValue": grade},
            "persistence": None,
            "isOptimistic": False,
        },
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "education.dataAwareAddEducationFormComponentstartDate",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "education.dataAwareAddEducationFormComponentstartDate"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "dateValue", "dateValue": {"$type": "proto.sdui.common.Date", "day": 0, "month": 0, "year": start_year}},
            "persistence": None,
            "isOptimistic": False,
        },
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "education.dataAwareAddEducationFormComponentendDate",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "education.dataAwareAddEducationFormComponentendDate"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "dateValue", "dateValue": {"$type": "proto.sdui.common.Date", "day": 0, "month": 0, "year": end_year}},
            "persistence": None,
            "isOptimistic": False,
        },
    ]
    lines = [
        'f:T%x,%s' % (max(len(description), 1), description),
        '10:T%x,%s' % (max(len(activities), 1), activities),
        '0:["$","$L1",null,{"modelStates":%s}]' % json.dumps(states, ensure_ascii=False),
    ]
    return """
<html>
  <body>
    <script>
      window.__como_rehydration__ = %s;
    </script>
  </body>
</html>
""" % json.dumps(lines, ensure_ascii=False)


def make_edit_form_rehydration_html(entries: list[str]) -> str:
    return """
<html>
  <body>
    <script>
      window.__como_rehydration__ = %s;
    </script>
  </body>
</html>
""" % json.dumps(entries, ensure_ascii=False)


def make_rehydration_text_entry(label: str, text: str) -> str:
    return f"{label}:T{len(text.encode('utf-8')):x},{text}"


def make_accessible_rsc_item_block(*, key: str, lines: list[str], urls: list[str] | None = None) -> str:
    children: list[str] = []
    for url in urls or []:
        children.append(f'["$","a",null,{{"href":"{url}"}}]')
    for line in lines:
        children.append(f'["$","p",null,{{"children":["{line}"]}}]')
    return f'["{{\\"key\\":\\"{key}\\",\\"semanticId\\":\\"\\",\\"threadlineDecoration\\":null}}",["$","div",null,{{"children":[{",".join(children)}]}}]]'


def make_accessible_experience_rsc_response_text(records: list[dict[str, str]]) -> str:
    blocks: list[str] = []
    for index, record in enumerate(records, start=1):
        lines = [record["title"]]
        company_line = record["company"]
        if record.get("employment_type"):
            company_line += f' · {record["employment_type"]}'
        lines.append(company_line)
        date_line = record["date_range"]
        if record.get("duration"):
            date_line += f' · {record["duration"]}'
        lines.append(date_line)
        if record.get("location"):
            lines.append(record["location"])
        if record.get("description"):
            lines.append(record["description"])
        lines.append(f'Skills for {record["title"]} at {record["company"]}')
        blocks.append(
            make_accessible_rsc_item_block(
                key=f"experience-item-{index}",
                lines=lines,
                urls=[record["company_url"]] if record.get("company_url") else [],
            )
        )
    return '0:[["$","$L1",null,{"modelStates":[],"isPartialPage":true}],"$undefined",[' + ",".join(blocks) + "]]"


def make_accessible_projects_rsc_response_text(records: list[dict[str, str]]) -> str:
    blocks: list[str] = []
    for index, record in enumerate(records, start=1):
        lines = [record["name"], record["date_range"]]
        if record.get("associated_with"):
            lines.append(f'Associated with {record["associated_with"]}')
        if record.get("description"):
            lines.append(record["description"])
        blocks.append(make_accessible_rsc_item_block(key=f"projects-item-{index}", lines=lines))
    return '0:[["$","$L1",null,{"modelStates":[],"isPartialPage":true}],"$undefined",[' + ",".join(blocks) + "]]"


def make_accessible_education_rsc_response_text(records: list[dict[str, str]]) -> str:
    blocks: list[str] = []
    for index, record in enumerate(records, start=1):
        lines = [record["school"]]
        if record.get("degree"):
            degree_line = record["degree"]
            if record.get("field_of_study"):
                degree_line += f', {record["field_of_study"]}'
            lines.append(degree_line)
        lines.append(record["date_range"])
        blocks.append(
            make_accessible_rsc_item_block(
                key=f"education-item-{index}",
                lines=lines,
                urls=[record["school_url"]] if record.get("school_url") else [],
            )
        )
    return '0:[["$","$L1",null,{"modelStates":[],"isPartialPage":true}],"$undefined",[' + ",".join(blocks) + "]]"


def make_accessible_licenses_rsc_response_text(records: list[dict[str, str]]) -> str:
    blocks: list[str] = []
    for index, record in enumerate(records, start=1):
        lines = [record["name"], record["issuer"]]
        if record.get("issue_date_text"):
            lines.append(f'Issued {record["issue_date_text"]}')
        if record.get("expiration_date_text"):
            lines.append(f'Expires {record["expiration_date_text"]}')
        if record.get("credential_id"):
            lines.append(f'Credential ID {record["credential_id"]}')
        if record.get("description"):
            lines.append(record["description"])
        if record.get("credential_url"):
            lines.append("Show credential")
        blocks.append(
            make_accessible_rsc_item_block(
                key=f"licenses-item-{index}",
                lines=lines,
                urls=[record["credential_url"]] if record.get("credential_url") else [],
            )
        )
    return '0:[["$","$L1",null,{"modelStates":[],"isPartialPage":true}],"$undefined",[' + ",".join(blocks) + "]]"


def build_projects_pagination_request(start: int, *, count: int = 10) -> dict:
    return {
        "$type": "proto.sdui.actions.requests.PaginationRequest",
        "pagerId": "com.linkedin.sdui.pagers.profile.details.projects",
        "requestedArguments": {
            "$type": "proto.sdui.actions.requests.RequestedArguments",
            "payload": {
                "start": start,
                "count": count,
                "vanityName": "alex-candidate",
                "profileId": "ACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbco",
            },
            "requestedStateKeys": [],
            "requestMetadata": {"$type": "proto.sdui.common.RequestMetadata"},
        },
        "trigger": {
            "$case": "itemDistanceTrigger",
            "itemDistanceTrigger": {
                "$type": "proto.sdui.actions.requests.ItemDistanceTrigger",
                "preloadDistance": 3,
                "preloadLength": 250,
            },
        },
        "retryCount": 2,
    }


PROJECTS_COMO_HTML = f"""
<html>
  <body>
    <script>
      window.__como_rehydration__ = {json.dumps(
          [
              '41:["$","$L3f",null,{{"observabilityIdentifier":"com.linkedin.sdui.pagers.profile.details.projects","children":["$","$L36",null,{{"componentKey":"com.linkedin.sdui.profile.card.refACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbcoProjectDetails","children":"$L6f"}}]}}]',
              '6f:["$","div",null,{{"data-testid":"lazy-column","data-component-type":"LazyColumn","children":["$undefined","$L94","$undefined","$undefined"]}}]',
              '94:["$","$La4",null,{{"children":["$","$L33",null,{{"paginationNeeded":true,"children":"$La5"}}]}}]',
              f'a5:["$","$Lc7",null,{{"nextPageRequest":{json.dumps(build_projects_pagination_request(0), ensure_ascii=False)}}}]',
          ],
          ensure_ascii=False,
      )};
    </script>
  </body>
</html>
"""


def make_projects_rsc_response_text(records: list[dict[str, object]], *, next_start: int | None = None) -> str:
    blocks = []
    for index, record in enumerate(records, start=1):
        edit_form_id = int(record.get("edit_form_id", index))
        lines = [
            str(record["name"]),
            str(record.get("date_range", "")),
            *(["Associated with " + str(record["associated_with"])] if record.get("associated_with") else []),
            *(str(item) for item in record.get("raw_lines", [])),
        ]
        children = [f'["$","p",null,{{"children":["{line}"]}}]' for line in lines if line]
        children.append(f'["$","button",null,{{"aria-label":"Edit project {record["name"]}","children":[]}}]')
        children.append(f'["$","a",null,{{"href":"https://www.linkedin.com/in/alex-candidate/details/projects/edit/forms/{edit_form_id}/"}}]')
        blocks.append(
            f'[\"{{\\\"key\\\":\\\"project-{index}\\\"}}\",[\"$\",\"div\",null,{{\"children\":[{",".join(children)}]}}]]'
        )
    response = '0:[[\"$\",\"$L1\",null,{\"modelStates\":[],\"isPartialPage\":true}]'
    if next_start is not None:
        response += "," + json.dumps(json.dumps(build_projects_pagination_request(next_start)), ensure_ascii=False)
    response += ',\"projects-page\",[' + ",".join(blocks) + "]]"
    return response


def make_project_edit_form_html(
    *,
    name: str,
    description: str,
    project_url: str,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
    currently_working: bool = False,
) -> str:
    states = [
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "auto-binding-testProjectFormname",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "auto-binding-testProjectFormname"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "stringValue", "stringValue": name},
            "persistence": None,
            "isOptimistic": False,
        },
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "auto-binding-testProjectFormdescription",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "auto-binding-testProjectFormdescription"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "stringValue", "stringValue": description},
            "persistence": None,
            "isOptimistic": False,
        },
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "auto-binding-testProjectFormlegacyProjectUrl",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "auto-binding-testProjectFormlegacyProjectUrl"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "stringValue", "stringValue": project_url},
            "persistence": None,
            "isOptimistic": False,
        },
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "auto-binding-testProjectFormcurrentlyWorking",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "auto-binding-testProjectFormcurrentlyWorking"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "stringValue", "stringValue": "Checked" if currently_working else ""},
            "persistence": None,
            "isOptimistic": False,
        },
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "auto-binding-testProjectFormstartDate",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "auto-binding-testProjectFormstartDate"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "dateValue", "dateValue": {"$type": "proto.sdui.common.Date", "day": 0, "month": start_month, "year": start_year}},
            "persistence": None,
            "isOptimistic": False,
        },
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "auto-binding-testProjectFormendDate",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "auto-binding-testProjectFormendDate"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "dateValue", "dateValue": {"$type": "proto.sdui.common.Date", "day": 0, "month": end_month, "year": end_year}},
            "persistence": None,
            "isOptimistic": False,
        },
    ]
    lines = [
        '0:["$","$L1",null,{"modelStates":%s}]' % json.dumps(states, ensure_ascii=False),
    ]
    return """
<html>
  <body>
    <script>
      window.__como_rehydration__ = %s;
    </script>
  </body>
</html>
""" % json.dumps(lines, ensure_ascii=False)


def make_project_edit_form_html_with_corrupted_description_ref(
    *,
    name: str,
    project_url: str,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
    currently_working: bool = False,
) -> str:
    html = make_project_edit_form_html(
        name=name,
        description="$f",
        project_url=project_url,
        start_year=start_year,
        start_month=start_month,
        end_year=end_year,
        end_month=end_month,
        currently_working=currently_working,
    )
    injected = 'f:T4ba,Crawler designed for monitoring. BROWSER_LOCAL_STORAGE tracker payload'
    return html.replace(
        "];\n    </script>",
        f', {json.dumps(injected, ensure_ascii=False)}];\n    </script>',
    )


def build_experience_pagination_request(start: int, *, count: int = 10) -> dict:
    return {
        "$type": "proto.sdui.actions.requests.PaginationRequest",
        "pagerId": "com.linkedin.sdui.pagers.profile.details.experience",
        "requestedArguments": {
            "$type": "proto.sdui.actions.requests.RequestedArguments",
            "payload": {
                "start": start,
                "count": count,
                "vanityName": "alex-candidate",
                "profileId": "ACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbco",
            },
            "requestedStateKeys": [],
            "requestMetadata": {"$type": "proto.sdui.common.RequestMetadata"},
        },
        "trigger": {
            "$case": "itemDistanceTrigger",
            "itemDistanceTrigger": {
                "$type": "proto.sdui.actions.requests.ItemDistanceTrigger",
                "preloadDistance": 3,
                "preloadLength": 250,
            },
        },
        "retryCount": 2,
    }


EXPERIENCE_COMO_HTML = f"""
<html>
  <body>
    <script>
      window.__como_rehydration__ = {json.dumps(
          [
              '41:["$","$L3f",null,{{"observabilityIdentifier":"com.linkedin.sdui.pagers.profile.details.experience","children":["$","$L36",null,{{"componentKey":"com.linkedin.sdui.profile.card.refACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbcoExperienceDetails","children":"$L6f"}}]}}]',
              '6f:["$","div",null,{{"data-testid":"lazy-column","data-component-type":"LazyColumn","children":["$undefined","$L94","$undefined","$undefined"]}}]',
              '94:["$","$La4",null,{{"children":["$","$L33",null,{{"paginationNeeded":true,"children":"$La5"}}]}}]',
              f'a5:["$","$Lc7",null,{{"nextPageRequest":{json.dumps(build_experience_pagination_request(0), ensure_ascii=False)}}}]',
          ],
          ensure_ascii=False,
      )};
    </script>
  </body>
</html>
"""


def make_experience_rsc_response_text(records: list[dict[str, str]], *, next_start: int | None = None) -> str:
    blocks = []
    for index, record in enumerate(records, start=1):
        company_url = record.get("company_url", "")
        employment_type = record.get("employment_type", "")
        company_duration = record.get("company_duration", "")
        company_meta = " · ".join(part for part in (employment_type, company_duration) if part)
        date_line = " · ".join(part for part in (record.get("date_range", ""), record.get("duration", "")) if part)
        parts = [
            f'["$","a",null,{{"href":"{company_url}"}}]',
            f'["$","p",null,{{"children":["{record["company"]}"]}}]',
        ]
        if company_meta:
            parts.append(f'["$","p",null,{{"children":["{company_meta}"]}}]')
        if record.get("company_location"):
            parts.append(f'["$","p",null,{{"children":["{record["company_location"]}"]}}]')
        parts.extend(
            [
                f'["$","$L7",null,{{"buttonProps":{{"aria-label":"Edit {record["title"]} at {record["company"]}"}}}}]',
                f'["$","a",null,{{"href":"https://www.linkedin.com/in/alex-candidate/details/experience/edit/forms/{index}/"}}]',
                f'["$","p",null,{{"children":["{record["title"]}"]}}]',
            ]
        )
        if date_line:
            parts.append(f'["$","p",null,{{"children":["{date_line}"]}}]')
        if record.get("location"):
            parts.append(f'["$","p",null,{{"children":["{record["location"]}"]}}]')
        for paragraph in record.get("description", "").split("\n"):
            if paragraph:
                parts.append(f'["$","p",null,{{"children":["{paragraph}"]}}]')
        if record.get("extra_line"):
            parts.append(f'["$","p",null,{{"children":["{record["extra_line"]}"]}}]')
        blocks.append(
            f'[\"{{\\\"key\\\":\\\"experience-{index}\\\"}}\",[\"$\",\"div\",null,{{\"componentKey\":\"com.linkedin.sdui.profile.position(ACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbco, {index})\",\"children\":[{",".join(parts)}]}}]]'
        )
    response = '0:[[\"$\",\"$L1\",null,{\"modelStates\":[],\"isPartialPage\":true}]'
    if next_start is not None:
        response += "," + json.dumps(json.dumps(build_experience_pagination_request(next_start)), ensure_ascii=False)
    response += ',\"experience-page\",[' + ",".join(blocks) + "]]"
    return response


def make_experience_edit_form_html(
    *,
    title: str,
    company: str,
    employment_type_value: str,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
    description: str,
    location: str,
    location_type: str = "",
) -> str:
    description_ref = "$f" if description else ""
    states = [
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "auto-binding-testProfilePositionFormtitle",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "auto-binding-testProfilePositionFormtitle"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "stringValue", "stringValue": title},
            "persistence": None,
            "isOptimistic": False,
        },
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "auto-binding-testProfilePositionFormcompanyName",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "auto-binding-testProfilePositionFormcompanyName"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "stringValue", "stringValue": company},
            "persistence": None,
            "isOptimistic": False,
        },
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "auto-binding-testProfilePositionFormemploymentType",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "auto-binding-testProfilePositionFormemploymentType"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "stringValue", "stringValue": employment_type_value},
            "persistence": None,
            "isOptimistic": False,
        },
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "auto-binding-testProfilePositionFormdescription",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "auto-binding-testProfilePositionFormdescription"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "stringValue", "stringValue": description_ref},
            "persistence": None,
            "isOptimistic": False,
        },
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "auto-binding-testProfilePositionForminitialDescription",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "auto-binding-testProfilePositionForminitialDescription"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "stringValue", "stringValue": description_ref},
            "persistence": None,
            "isOptimistic": False,
        },
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "auto-binding-testProfilePositionFormlocation",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "auto-binding-testProfilePositionFormlocation"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "stringValue", "stringValue": location},
            "persistence": None,
            "isOptimistic": False,
        },
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "auto-binding-testProfilePositionFormlocationType",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "auto-binding-testProfilePositionFormlocationType"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "stringValue", "stringValue": location_type},
            "persistence": None,
            "isOptimistic": False,
        },
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "auto-binding-testProfilePositionFormstartDate",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "auto-binding-testProfilePositionFormstartDate"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "dateValue", "dateValue": {"$type": "proto.sdui.common.Date", "day": 0, "month": start_month, "year": start_year}},
            "persistence": None,
            "isOptimistic": False,
        },
        {
            "$type": "proto.sdui.State",
            "stateKey": "",
            "key": {
                "$type": "proto.sdui.StateKey",
                "value": "auto-binding-testProfilePositionFormendDate",
                "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "auto-binding-testProfilePositionFormendDate"}},
                "namespace": "MemoryNamespace",
                "isEncrypted": False,
            },
            "value": {"$case": "dateValue", "dateValue": {"$type": "proto.sdui.common.Date", "day": 0, "month": end_month, "year": end_year}},
            "persistence": None,
            "isOptimistic": False,
        },
    ]
    lines = [
        'f:T%x,%s' % (max(len(description), 1), description),
        '10:T%x,%s' % (max(len(description), 1), description),
        '0:["$","$L1",null,{"modelStates":%s}]' % json.dumps(states, ensure_ascii=False),
        '1:["$","select",null,{"valueStateKey":{"value":"auto-binding-testProfilePositionFormemploymentType"},"options":%s}]'
        % json.dumps(
            [
                {"label": "Please select", "value": ""},
                {"label": "Full-time", "value": "12"},
                {"label": "Part-time", "value": "11"},
                {"label": "Freelance", "value": "20"},
                {"label": "Contract", "value": "2"},
            ],
            ensure_ascii=False,
        ),
    ]
    return """
<html>
  <body>
    <script>
      window.__como_rehydration__ = %s;
    </script>
  </body>
</html>
""" % json.dumps(lines, ensure_ascii=False)


def build_certifications_pagination_request(start: int, *, count: int = 10) -> dict:
    return {
        "$type": "proto.sdui.actions.requests.PaginationRequest",
        "pagerId": "com.linkedin.sdui.pagers.profile.details.certifications",
        "requestedArguments": {
            "$type": "proto.sdui.actions.requests.RequestedArguments",
            "payload": {
                "start": start,
                "count": count,
                "vanityName": "alex-candidate",
                "profileId": "ACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbco",
            },
            "requestedStateKeys": [],
            "requestMetadata": {"$type": "proto.sdui.common.RequestMetadata"},
        },
        "trigger": {
            "$case": "itemDistanceTrigger",
            "itemDistanceTrigger": {
                "$type": "proto.sdui.actions.requests.ItemDistanceTrigger",
                "preloadDistance": 3,
                "preloadLength": 250,
            },
        },
        "retryCount": 2,
    }


CERTIFICATIONS_COMO_HTML = f"""
<html>
  <body>
    <script>
      window.__como_rehydration__ = {json.dumps(
          [
              '41:["$","$L3f",null,{{"observabilityIdentifier":"com.linkedin.sdui.pagers.profile.details.certifications","children":["$","$L36",null,{{"componentKey":"com.linkedin.sdui.profile.card.refACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbcoCertificationDetails","children":"$L6f"}}]}}]',
              '6f:["$","div",null,{{"data-testid":"lazy-column","data-component-type":"LazyColumn","children":["$undefined","$L94","$undefined","$undefined"]}}]',
              '94:["$","$La4",null,{{"children":["$","$L33",null,{{"paginationNeeded":true,"children":"$La5"}}]}}]',
              f'a5:["$","$Lc7",null,{{"nextPageRequest":{json.dumps(build_certifications_pagination_request(0), ensure_ascii=False)}}}]',
          ],
          ensure_ascii=False,
      )};
    </script>
  </body>
</html>
"""


def make_certifications_rsc_response_text(records: list[dict[str, str]], *, next_start: int | None = None) -> str:
    blocks = []
    for index, record in enumerate(records, start=1):
        parts = [
            f'["$","$L7",null,{{"buttonProps":{{"aria-label":"Edit {record["name"]} certification"}}}}]',
            f'["$","a",null,{{"href":"https://www.linkedin.com/in/alex-candidate/details/certifications/edit/forms/{index}/"}}]',
            f'["$","p",null,{{"children":["{record["name"]}"]}}]',
        ]
        if record.get("issuer"):
            parts.append(f'["$","p",null,{{"children":["{record["issuer"]}"]}}]')
        if record.get("issue_date_text"):
            parts.append(f'["$","p",null,{{"children":["Issued {record["issue_date_text"]}"]}}]')
        if record.get("expiration_date_text"):
            parts.append(f'["$","p",null,{{"children":["Expires {record["expiration_date_text"]}"]}}]')
        if record.get("credential_id"):
            parts.append(f'["$","p",null,{{"children":["Credential ID {record["credential_id"]}"]}}]')
        if record.get("credential_url"):
            parts.append(f'["$","a",null,{{"href":"{record["credential_url"]}"}}]')
            parts.append(f'["$","p",null,{{"children":["Credential URL {record["credential_url"]}"]}}]')
        if record.get("description"):
            parts.append(f'["$","p",null,{{"children":["{record["description"]}"]}}]')
        blocks.append(
            f'[\"{{\\\"key\\\":\\\"certification-{index}\\\"}}\",[\"$\",\"div\",null,{{\"componentKey\":\"com.linkedin.sdui.profile.certification(ACoAAALVS1ABzRQykLW_oCkidqdRm_a6w8wZbco, {index})\",\"children\":[{",".join(parts)}]}}]]'
        )
    response = '0:[[\"$\",\"$L1\",null,{\"modelStates\":[],\"isPartialPage\":true}]'
    if next_start is not None:
        response += "," + json.dumps(json.dumps(build_certifications_pagination_request(next_start)), ensure_ascii=False)
    response += ',\"certifications-page\",[' + ",".join(blocks) + "]]"
    return response


class FakeLocator:
    def __init__(self, name: str, *, visible: bool = True, click_callback=None, inner_html: str = ""):
        self.name = name
        self.visible = visible
        self.clicks = 0
        self.click_callback = click_callback
        self._inner_html = inner_html

    def first(self):
        return self

    def is_visible(self, timeout: int | None = None):
        return self.visible

    def click(self, timeout: int | None = None):
        self.clicks += 1
        if self.click_callback is not None:
            self.click_callback()

    def inner_html(self, timeout: int | None = None):
        return self._inner_html


class FakeKeyboard:
    def __init__(self, page):
        self.page = page
        self.presses = []

    def press(self, key: str):
        self.presses.append(key)
        if key == "Escape":
            self.page.dialog_html = None


class FakePage:
    def __init__(self, html: str = PUBLIC_PROFILE_HTML, url: str = "https://www.linkedin.com/in/demo-profile/"):
        self._html = html
        self.url = url
        self.goto_calls = []
        self.locators = {}
        self.disallowed_clicks = []
        self.evaluate_calls = []
        self.listeners = {}
        self.dialog_html = None
        self.keyboard = FakeKeyboard(self)

    def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int | None = None):
        self.goto_calls.append((url, wait_until, timeout))
        self.url = url

    def wait_for_load_state(self, state: str, timeout: int | None = None):
        if state == "networkidle":
            raise AssertionError("LinkedIn browser flows must not wait for networkidle")

    def locator(self, selector: str):
        if "Connect" in selector or "Message" in selector or "Follow" in selector:
            self.disallowed_clicks.append(selector)
            return FakeLocator(selector, visible=True)
        locator = self.locators.setdefault(selector, FakeLocator(selector, visible=False))
        return locator

    def on(self, event: str, callback):
        self.listeners.setdefault(event, []).append(callback)

    def evaluate(self, script: str, arg=None):
        self.evaluate_calls.append(script)

    def content(self):
        if self.dialog_html:
            return f"{self._html}\n{self.dialog_html}"
        return self._html


class FakeRequest:
    def __init__(self, payload: dict | None = None):
        self._payload = payload

    def post_data(self):
        if self._payload is None:
            return None
        return json.dumps(self._payload)

    def post_data_json(self):
        return self._payload


class FakeResponse:
    def __init__(
        self,
        *,
        url: str,
        payload: dict | None = None,
        text_value: str | None = None,
        content_type: str = "application/json",
        request_payload: dict | None = None,
    ):
        self.url = url
        self._payload = payload
        self._text_value = text_value
        self._content_type = content_type
        self.request = FakeRequest(request_payload)

    @property
    def headers(self):
        return {"content-type": self._content_type}

    def text(self):
        if self._text_value is not None:
            return self._text_value
        return json.dumps(self._payload)


class DeepFakePage(FakePage):
    def __init__(self):
        super().__init__(html=DEEP_MAIN_PROFILE_HTML, url="https://www.linkedin.com/in/alex-candidate/")
        self.routes = {
            "https://www.linkedin.com/in/me/": DEEP_MAIN_PROFILE_HTML,
            "https://www.linkedin.com/in/alex-candidate/": DEEP_MAIN_PROFILE_HTML,
            "https://www.linkedin.com/in/alex-candidate/details/experience/": DETAIL_EXPERIENCE_HTML,
        }
        self.emitted_relevant_response = False
        self.emitted_irrelevant_response = False

    def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int | None = None):
        self.goto_calls.append((url, wait_until, timeout))
        self.url = url
        self._html = self.routes.get(url, self._html)
        self.dialog_html = None

    def locator(self, selector: str):
        if "Connect" in selector or "Message" in selector or "Follow" in selector:
            self.disallowed_clicks.append(selector)
            return FakeLocator(selector, visible=True)
        lowered = selector.lower()
        if "show all" in lowered and ("experience" in lowered or "details/experience" in lowered):
            return FakeLocator(
                selector,
                visible=self.url.endswith("/alex-candidate/") or self.url.endswith("/in/me/"),
                click_callback=lambda: self.goto(
                    "https://www.linkedin.com/in/alex-candidate/details/experience/",
                    wait_until="domcontentloaded",
                ),
            )
        if "[role='dialog']" in lowered:
            return FakeLocator(selector, visible=self.dialog_html is not None, inner_html=self.dialog_html or "")
        return super().locator(selector)

    def evaluate(self, script: str, arg=None):
        self.evaluate_calls.append(script)
        listeners = self.listeners.get("response", [])
        if not self.emitted_irrelevant_response:
            self.emitted_irrelevant_response = True
            for callback in listeners:
                callback(
                    FakeResponse(
                        url="https://www.linkedin.com/voyager/api/feed",
                        payload={"feed": [{"text": "ignore me"}]},
                    )
                )
        if not self.emitted_relevant_response:
            self.emitted_relevant_response = True
            for callback in listeners:
                callback(
                    FakeResponse(
                        url="https://www.linkedin.com/voyager/api/identity/profiles/alex-candidate/languages",
                        payload={
                            "profileId": "alex-candidate",
                            "languages": [{"name": "English"}, {"name": "Spanish"}],
                            "about": "Builds SOAR playbooks with measurable incident outcomes for global teams.",
                        },
                    )
                )


class HtmlRouteOnlyDeepFakePage(DeepFakePage):
    def locator(self, selector: str):
        lowered = selector.lower()
        if "show all" in lowered and ("experience" in lowered or "details/experience" in lowered):
            return FakeLocator(selector, visible=False)
        return super().locator(selector)


class ConstructedRouteDeepFakePage(DeepFakePage):
    def __init__(self):
        super().__init__()
        self.routes["https://www.linkedin.com/in/alex-candidate/"] = CANONICAL_OWN_PROFILE_HTML

    def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int | None = None):
        self.goto_calls.append((url, wait_until, timeout))
        if url == "https://www.linkedin.com/in/me/":
            self.url = "https://www.linkedin.com/in/alex-candidate/"
            self._html = CANONICAL_OWN_PROFILE_HTML
            self.dialog_html = None
            return
        super().goto(url, wait_until=wait_until, timeout=timeout)

    def locator(self, selector: str):
        lowered = selector.lower()
        if "show all" in lowered or "details/experience" in lowered:
            return FakeLocator(selector, visible=False)
        return super().locator(selector)


class RedirectingFakePage(FakePage):
    def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int | None = None):
        self.goto_calls.append((url, wait_until, timeout))
        self.url = "https://www.linkedin.com/in/alex-candidate/"


class FeedLoginPage(FakePage):
    def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int | None = None):
        self.goto_calls.append((url, wait_until, timeout))
        self.url = "https://www.linkedin.com/feed/"


class SkillsRscDeepFakePage(ConstructedRouteDeepFakePage):
    def __init__(self):
        super().__init__()
        self.routes.pop("https://www.linkedin.com/in/alex-candidate/details/experience/", None)
        self.routes["https://www.linkedin.com/in/alex-candidate/details/skills/"] = EMPTY_SKILLS_DETAIL_HTML
        self.emitted_skills_rsc = False
        self.emitted_unrelated_rsc = False

    def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int | None = None):
        super().goto(url, wait_until=wait_until, timeout=timeout)
        listeners = self.listeners.get("response", [])
        if self.url.endswith("/details/skills/") and not self.emitted_unrelated_rsc:
            self.emitted_unrelated_rsc = True
            for callback in listeners:
                callback(
                    FakeResponse(
                        url="https://www.linkedin.com/flagship-web/rsc-action/actions/pagination?sduiid=com.linkedin.sdui.pagers.profile.details.languages&parentSpanId=ignore-me",
                        text_value=UNRELATED_RSC_RESPONSE_TEXT,
                        content_type="text/x-component",
                    )
                )
        if self.url.endswith("/details/skills/") and not self.emitted_skills_rsc:
            self.emitted_skills_rsc = True
            for callback in listeners:
                callback(
                    FakeResponse(
                        url="https://www.linkedin.com/flagship-web/rsc-action/actions/pagination?sduiid=com.linkedin.sdui.pagers.profile.details.skills&parentSpanId=volatile-span",
                        text_value=SKILLS_RSC_RESPONSE_TEXT,
                        content_type="text/x-component",
                    )
                )

    def evaluate(self, script: str, arg=None):
        self.evaluate_calls.append(script)


class SkillsCountRscDeepFakePage(ConstructedRouteDeepFakePage):
    def __init__(self):
        super().__init__()
        self.routes.pop("https://www.linkedin.com/in/alex-candidate/details/experience/", None)
        self.routes["https://www.linkedin.com/in/alex-candidate/"] = SKILLS_COUNT_MAIN_PROFILE_HTML
        self.routes["https://www.linkedin.com/in/alex-candidate/details/skills/"] = EMPTY_SKILLS_DETAIL_HTML
        self.auto_starts = [0]
        self.manual_request_starts = []
        self.skills_batches_by_start = {
            0: make_skills_rsc_response_text([f"Skill {index}" for index in range(1, 11)], next_start=10),
            10: make_skills_rsc_response_text([f"Skill {index}" for index in range(11, 21)], next_start=20),
            20: make_skills_rsc_response_text([f"Skill {index}" for index in range(21, 26)], next_start=30),
        }

    def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int | None = None):
        self.goto_calls.append((url, wait_until, timeout))
        if url == "https://www.linkedin.com/in/me/":
            self.url = "https://www.linkedin.com/in/alex-candidate/"
            self._html = self.routes["https://www.linkedin.com/in/alex-candidate/"]
            self.dialog_html = None
            return
        super().goto(url, wait_until=wait_until, timeout=timeout)
        if self.url.endswith("/details/skills/") and self.auto_starts:
            self._emit_skills_response(self.auto_starts.pop(0))

    def _emit_skills_response(self, start: int):
        response_text = self.skills_batches_by_start.get(start)
        if response_text is None:
            return
        listeners = self.listeners.get("response", [])
        for callback in listeners:
            callback(
                FakeResponse(
                    url="https://www.linkedin.com/flagship-web/rsc-action/actions/pagination?sduiid=com.linkedin.sdui.pagers.profile.details.skills&parentSpanId=batch-span",
                    text_value=response_text,
                    content_type="text/x-component",
                )
            )

    def evaluate(self, script: str, arg=None):
        self.evaluate_calls.append(script)
        if not self.url.endswith("/details/skills/"):
            return
        if arg and isinstance(arg, dict):
            payload = arg.get("payload", {})
            pagination_request = payload.get("paginationRequest", {})
            start = pagination_request.get("requestedArguments", {}).get("payload", {}).get("start")
            if isinstance(start, int):
                self.manual_request_starts.append(start)
                self._emit_skills_response(start)
            return


class SkillsEarlyStopRscDeepFakePage(SkillsCountRscDeepFakePage):
    def __init__(self):
        super().__init__()

    def evaluate(self, script: str, arg=None):
        self.evaluate_calls.append(script)
        if arg and isinstance(arg, dict):
            payload = arg.get("payload", {})
            pagination_request = payload.get("paginationRequest", {})
            start = pagination_request.get("requestedArguments", {}).get("payload", {}).get("start")
            if isinstance(start, int):
                self.manual_request_starts.append(start)
            return


class LanguagesRouteDeepFakePage(ConstructedRouteDeepFakePage):
    def __init__(self):
        super().__init__()
        self.routes["https://www.linkedin.com/in/alex-candidate/"] = LANGUAGES_ROUTE_MAIN_PROFILE_HTML
        self.routes.pop("https://www.linkedin.com/in/alex-candidate/details/skills/", None)

    def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int | None = None):
        self.goto_calls.append((url, wait_until, timeout))
        if url == "https://www.linkedin.com/in/me/":
            self.url = "https://www.linkedin.com/in/alex-candidate/"
            self._html = self.routes["https://www.linkedin.com/in/alex-candidate/"]
            self.dialog_html = None
            return
        super().goto(url, wait_until=wait_until, timeout=timeout)


class FlakyContentAccessiblePage(ConstructedRouteDeepFakePage):
    def __init__(self):
        super().__init__()
        self.remaining_content_failures = 2

    def content(self):
        if self.remaining_content_failures > 0:
            self.remaining_content_failures -= 1
            raise RuntimeError("Page.content: Unable to retrieve content because the page is navigating and changing the content.")
        return super().content()


class FakeContext:
    def __init__(self, page: FakePage):
        self.page = page
        self.closed = False
        self.cookies_written = False

    def new_page(self):
        return self.page

    def storage_state(self, path: str | None = None):
        if path:
            Path(path).write_text(json.dumps({"cookies": []}), encoding="utf-8")
            self.cookies_written = True
        return {"cookies": []}

    def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self, context: FakeContext):
        self.context = context
        self.new_context_args = []
        self.closed = False

    def new_context(self, *args, **kwargs):
        self.new_context_args.append((args, kwargs))
        return self.context

    def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, context: FakeContext):
        self.context = context
        self.launch_args = []
        self.launch_persistent_args = []

    def launch_persistent_context(self, *args, **kwargs):
        self.launch_persistent_args.append((args, kwargs))
        return self.context

    def launch(self, *args, **kwargs):
        self.launch_args.append((args, kwargs))
        return FakeBrowser(self.context)


class FakePlaywright:
    def __init__(self, context: FakeContext):
        self.chromium = FakeChromium(context)


class FakePlaywrightManager:
    def __init__(self, context: FakeContext):
        self.playwright = FakePlaywright(context)

    def __enter__(self):
        return self.playwright

    def __exit__(self, exc_type, exc, tb):
        return False


def write_session_state(app_home: str, profile_name: str, *, cookies: list[dict] | None = None) -> Path:
    path = linkedin_cv.session_state_path(app_home, profile_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "cookies": cookies or [
            {
                "name": "JSESSIONID",
                "value": '"ajax:token"',
                "domain": ".linkedin.com",
                "path": "/",
            }
        ],
        "origins": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class LinkedInCVTests(unittest.TestCase):
    def test_profile_id_builds_canonical_linkedin_url(self):
        self.assertEqual(
            linkedin_cv.build_profile_url(profile_id="demo-profile"),
            "https://www.linkedin.com/in/demo-profile/",
        )

    def test_validate_profile_url_rejects_non_profile_surfaces(self):
        blocked_urls = [
            "https://www.linkedin.com/search/results/people/?keywords=security",
            "https://www.linkedin.com/feed/",
            "https://www.linkedin.com/mynetwork/",
            "https://www.linkedin.com/jobs/view/123",
            "https://www.linkedin.com/company/example",
        ]

        for url in blocked_urls:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    linkedin_cv.validate_profile_url(url)

    def test_accessible_capture_requires_confirmation(self):
        result = linkedin_cv.capture_accessible_profile(
            profile_name="personal",
            profile_id="demo-profile",
            confirm_accessible_profile_capture=False,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["exit_code"], 2)
        self.assertIn("--confirm-accessible-profile-capture", result["stderr"])

    def test_capture_refuses_search_url_before_browser_launch(self):
        result = linkedin_cv.capture_accessible_profile(
            profile_name="personal",
            url="https://www.linkedin.com/search/results/people/?keywords=security",
            confirm_accessible_profile_capture=True,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["result"]["status"], "invalid_profile_url")

    def test_parse_profile_html_extracts_cv_fields(self):
        profile = linkedin_cv.parse_profile_html(
            PUBLIC_PROFILE_HTML,
            profile_url="https://www.linkedin.com/in/demo-profile/",
            capture_type="accessible_profile",
        )

        self.assertEqual(profile["name"], "Jane Candidate")
        self.assertIn("alert fatigue", profile["headline"])
        self.assertIn("threat detection", profile["about"])
        self.assertIn("Lead Security Engineer at ExampleCo", profile["experience"])
        self.assertIn("Detection Engineering", profile["skills"])
        self.assertEqual(profile["visibility"]["status"], "ok")

    def test_parse_profile_html_extracts_about_from_expandable_text_box(self):
        profile = linkedin_cv.parse_profile_html(
            ABOUT_EXPANDABLE_HTML,
            profile_url="https://www.linkedin.com/in/alex-candidate/",
            capture_type="own_profile",
        )

        self.assertIn("With over a decade in cybersecurity", profile["about"])
        self.assertNotIn("Edit", profile["about"])
        self.assertNotIn("Top skills", profile["about"])

    def test_parse_profile_html_keeps_richer_nested_section_candidate(self):
        profile = linkedin_cv.parse_profile_html(
            NESTED_RICH_SECTION_HTML,
            profile_url="https://www.linkedin.com/in/alex-candidate/",
            capture_type="own_profile",
        )

        self.assertIn("Lead Security Engineer at ExampleCo", profile["experience"])

    def test_parse_profile_html_detects_sign_in_and_checkpoint_states(self):
        sign_in = linkedin_cv.parse_profile_html(
            '<html><body><form action="/uas/login-submit"><input name="session_key"></form></body></html>',
            profile_url="https://www.linkedin.com/in/demo-profile/",
            capture_type="accessible_profile",
        )
        checkpoint = linkedin_cv.parse_profile_html(
            '<html><body><main><h1>Security verification</h1><form action="/checkpoint/challenge"></form></main></body></html>',
            profile_url="https://www.linkedin.com/in/demo-profile/",
            capture_type="accessible_profile",
        )

        self.assertEqual(sign_in["visibility"]["status"], "sign_in_required")
        self.assertEqual(checkpoint["visibility"]["status"], "checkpoint_required")

    def test_parse_profile_html_prefers_name_adjacent_headline_and_canonical_profile_url(self):
        profile = linkedin_cv.parse_profile_html(
            OWN_PROFILE_RICH_HTML,
            profile_url="https://www.linkedin.com/in/me/",
            capture_type="own_profile",
        )

        self.assertEqual(profile["name"], "Alex Candidate")
        self.assertEqual(profile["profile_url"], "https://www.linkedin.com/in/alex-candidate/")
        self.assertEqual(profile["profile_id"], "alex-candidate")
        self.assertEqual(
            profile["headline"],
            "Senior Detection Engineer | Security Automation | Incident Response",
        )
        self.assertEqual(profile["location"], "Berlin, Germany")

    def test_merge_profile_snapshots_prefers_detail_dom_and_uses_network_for_thinner_sections(self):
        inline = linkedin_cv.parse_profile_html(
            THIN_OWN_PROFILE_HTML,
            profile_url="https://www.linkedin.com/in/alex-candidate/",
            capture_type="own_profile",
        )
        detail = linkedin_cv.parse_profile_html(
            DETAIL_EXPERIENCE_HTML,
            profile_url="https://www.linkedin.com/in/alex-candidate/details/experience/",
            capture_type="own_profile",
        )

        merged = linkedin_cv.merge_profile_snapshots(
            inline,
            detail_snapshots=[detail],
            network_sections={
                "about": "Builds SOAR playbooks with measurable incident outcomes for global teams.",
                "languages": ["English", "Spanish"],
            },
        )

        self.assertEqual(merged["capture_depth"], "deep")
        self.assertEqual(
            merged["experience"],
            ["Senior Security Engineer at ExampleCo", "Incident Response Lead at PreviousCo"],
        )
        self.assertEqual(
            merged["about"],
            "Builds SOAR playbooks with measurable incident outcomes for global teams.",
        )
        self.assertEqual(merged["languages"], ["English", "Spanish"])
        self.assertEqual(merged["section_sources"]["experience"], "detail_dom")
        self.assertEqual(merged["section_sources"]["about"], "network")
        self.assertEqual(merged["section_sources"]["languages"], "network")

    def test_extract_detail_route_section_handles_route_style_layouts(self):
        experience_items = linkedin_cv.extract_detail_route_section(
            ROUTE_STYLE_EXPERIENCE_HTML,
            section_key="experience",
        )
        language_items = linkedin_cv.extract_detail_route_section(
            ROUTE_STYLE_LANGUAGES_HTML,
            section_key="languages",
        )

        self.assertEqual(
            experience_items,
            ["Senior Security Engineer 2023 - Present", "Incident Response Lead 2021 - 2023"],
        )
        self.assertEqual(
            language_items,
            ["English - Full professional proficiency", "Spanish - Native or bilingual proficiency"],
        )

    def test_extract_skills_from_rsc_text_ignores_project_evidence(self):
        skills = linkedin_cv._extract_skills_from_rsc_text(SKILLS_RSC_RESPONSE_TEXT)

        self.assertEqual(
            skills,
            [
                "Software Architecture",
                "Systems Programming",
                "Rust (Programming Language)",
                "Event Tracing for Windows (ETW)",
                "SIGMA Rules",
            ],
        )
        self.assertNotIn("RedCurve — Local-First Endpoint Investigation Platform", skills)

    def test_extract_initial_skills_pagination_request_from_como_html(self):
        pagination_request = linkedin_cv._extract_skills_initial_pagination_request_from_html(SKILLS_COMO_HTML)

        self.assertIsNotNone(pagination_request)
        self.assertEqual(pagination_request["pagerId"], "com.linkedin.sdui.pagers.profile.details.skills")
        self.assertEqual(pagination_request["requestedArguments"]["payload"]["start"], 0)
        self.assertEqual(pagination_request["requestedArguments"]["payload"]["count"], 10)

    def test_extract_initial_languages_pagination_request_from_como_html(self):
        pagination_request = linkedin_cv._extract_languages_initial_pagination_request_from_html(LANGUAGES_COMO_HTML)

        self.assertIsNotNone(pagination_request)
        self.assertEqual(pagination_request["pagerId"], "com.linkedin.sdui.pagers.profile.details.languages")
        self.assertEqual(pagination_request["requestedArguments"]["payload"]["start"], 0)
        self.assertEqual(pagination_request["requestedArguments"]["payload"]["count"], 10)

    def test_extract_initial_education_pagination_request_from_como_html(self):
        pagination_request = linkedin_cv._extract_education_initial_pagination_request_from_html(EDUCATION_COMO_HTML)

        self.assertIsNotNone(pagination_request)
        self.assertEqual(pagination_request["pagerId"], "com.linkedin.sdui.pagers.profile.details.education")
        self.assertEqual(pagination_request["requestedArguments"]["payload"]["start"], 0)
        self.assertEqual(pagination_request["requestedArguments"]["payload"]["count"], 10)
        self.assertEqual(
            pagination_request["requestedArguments"]["payload"]["detailSectionReplaceableComponentRef"],
            "$L6f",
        )

    def test_extract_initial_projects_pagination_request_from_como_html(self):
        pagination_request = linkedin_cv._extract_projects_initial_pagination_request_from_html(PROJECTS_COMO_HTML)

        self.assertIsNotNone(pagination_request)
        self.assertEqual(pagination_request["pagerId"], "com.linkedin.sdui.pagers.profile.details.projects")
        self.assertEqual(pagination_request["requestedArguments"]["payload"]["start"], 0)
        self.assertEqual(pagination_request["requestedArguments"]["payload"]["count"], 10)

    def test_extract_languages_from_rsc_text(self):
        languages = linkedin_cv._extract_languages_from_rsc_text(
            make_languages_rsc_response_text(
                [
                    ("Francés", "Limited working proficiency"),
                    ("Inglés", "Full professional proficiency"),
                    ("Italiano", "Elementary proficiency"),
                ]
            )
        )

        self.assertEqual(
            languages,
            [
                "Francés - Limited working proficiency",
                "Inglés - Full professional proficiency",
                "Italiano - Elementary proficiency",
            ],
        )

    def test_extract_education_records_from_rsc_text(self):
        education = linkedin_cv._extract_education_records_from_rsc_text(
            make_education_rsc_response_text(
                [
                    {
                        "school": "Example University",
                        "school_url": "https://www.linkedin.com/school/29216/",
                        "degree": "Official Security Master's degree in Information and Communication Technologies",
                        "field_of_study": "Security",
                        "date_range": "2011 - 2012",
                        "raw_lines": ["Thesis: Malware traffic classification"],
                    }
                ]
            )
        )

        self.assertEqual(
            education,
            [
                {
                    "school": "Example University",
                    "school_url": "https://www.linkedin.com/school/29216/",
                    "degree": "Official Security Master's degree in Information and Communication Technologies",
                    "field_of_study": "Security",
                    "date_range": "2011 - 2012",
                    "start_date_text": "2011",
                    "end_date_text": "2012",
                    "grade": "",
                    "activities": "",
                    "description": "",
                    "raw_lines": ["Thesis: Malware traffic classification"],
                }
            ],
        )

    def test_extract_project_records_from_rsc_text(self):
        projects = linkedin_cv._extract_project_records_from_rsc_text(
            make_projects_rsc_response_text(
                [
                    {
                        "name": "RedCurve — Local-First Endpoint Investigation Platform",
                        "date_range": "Mar 2026 - Present",
                        "associated_with": "ExampleCo",
                        "raw_lines": ["Visible in fraud lab"],
                    }
                ]
            )
        )

        self.assertEqual(
            projects,
            [
                {
                    "name": "RedCurve — Local-First Endpoint Investigation Platform",
                    "date_range": "Mar 2026 - Present",
                    "start_date_text": "Mar 2026",
                    "end_date_text": "Present",
                    "is_current": True,
                    "associated_with": "ExampleCo",
                    "project_url": "",
                    "description": "",
                    "raw_lines": ["Visible in fraud lab"],
                }
            ],
        )

    def test_extract_project_records_keep_edit_form_urls_aligned_when_url_follows_content(self):
        bundles = linkedin_cv._extract_project_entry_bundles_from_rsc_text(
            make_projects_rsc_response_text(
                [
                    {
                        "edit_form_id": 11,
                        "name": "JScrambler Step by Step Deobfuscator",
                        "date_range": "Mar 2016 - Present",
                    },
                    {
                        "edit_form_id": 22,
                        "name": "Universal Crawler",
                        "date_range": "Jan 2016 - Present",
                        "associated_with": "Bank of Ireland",
                    },
                ]
            )
        )

        self.assertEqual(
            [(bundle["record"]["name"], bundle["edit_form_url"]) for bundle in bundles],
            [
                ("JScrambler Step by Step Deobfuscator", "/details/projects/edit/forms/11/"),
                ("Universal Crawler", "/details/projects/edit/forms/22/"),
            ],
        )

    def test_parse_edit_form_rehydration_builds_label_map_with_mixed_entries(self):
        states = [
            {
                "$type": "proto.sdui.State",
                "stateKey": "",
                "key": {
                    "$type": "proto.sdui.StateKey",
                    "value": "auto-binding-testDescription",
                    "key": {"$type": "proto.sdui.Key", "value": {"$case": "id", "id": "auto-binding-testDescription"}},
                    "namespace": "MemoryNamespace",
                    "isEncrypted": False,
                },
                "value": {"$case": "stringValue", "stringValue": "$f"},
                "persistence": None,
                "isOptimistic": False,
            }
        ]
        html = make_edit_form_rehydration_html(
            [
                make_rehydration_text_entry("f", "First paragraph\nstill first\n\nSecond paragraph"),
                '10:"Quoted plain value"',
                '1a:["$","div",null,{"children":["ignored"]}]',
                '0:["$","$L1",null,{"modelStates":%s}]' % json.dumps(states, ensure_ascii=False),
            ]
        )

        parsed = linkedin_cv._parse_edit_form_rehydration(html)

        self.assertEqual(list(parsed["entries"]), [
            make_rehydration_text_entry("f", "First paragraph\nstill first\n\nSecond paragraph"),
            '10:"Quoted plain value"',
            '1a:["$","div",null,{"children":["ignored"]}]',
            '0:["$","$L1",null,{"modelStates":%s}]' % json.dumps(states, ensure_ascii=False),
        ])
        self.assertEqual(
            parsed["labels"]["f"],
            make_rehydration_text_entry("f", "First paragraph\nstill first\n\nSecond paragraph").split(":", 1)[1],
        )
        self.assertEqual(parsed["labels"]["10"], '"Quoted plain value"')
        self.assertEqual(parsed["labels"]["1a"], '["$","div",null,{"children":["ignored"]}]')

    def test_parse_edit_form_rehydration_extracts_multiple_labels_from_one_top_level_entry(self):
        html = make_edit_form_rehydration_html(
            [
                '1:I["abc",[],"default"]\ne:I["def",[],"default"]\nf:Td,Resolved text\n10:"Quoted value"',
                '0:["$","$L1",null,{"modelStates":[]}]',
            ]
        )

        parsed = linkedin_cv._parse_edit_form_rehydration(html)

        self.assertEqual(parsed["labels"]["1"], 'I["abc",[],"default"]')
        self.assertEqual(parsed["labels"]["e"], 'I["def",[],"default"]')
        self.assertEqual(parsed["labels"]["f"], "Td,Resolved text")
        self.assertEqual(parsed["labels"]["10"], '"Quoted value"')

    def test_parse_edit_form_rehydration_stitches_split_text_payloads_by_declared_length(self):
        html = make_edit_form_rehydration_html(
            [
                'f:T1e,Alpha beta ga',
                'mma delta epsilon12:T5,ignore',
                '0:["$","$L1",null,{"modelStates":[]}]',
            ]
        )

        parsed = linkedin_cv._parse_edit_form_rehydration(html)

        self.assertEqual(parsed["labels"]["f"], "T1e,Alpha beta gamma delta epsilon")

    def test_parse_edit_form_rehydration_parses_adjacent_label_after_split_text(self):
        html = make_edit_form_rehydration_html(
            [
                make_rehydration_text_entry("f", "Hello world")[:-1],
                'd10:"Second value"',
                '0:["$","$L1",null,{"modelStates":[]}]',
            ]
        )

        parsed = linkedin_cv._parse_edit_form_rehydration(html)

        self.assertEqual(parsed["labels"]["f"], make_rehydration_text_entry("f", "Hello world").split(":", 1)[1])
        self.assertEqual(parsed["labels"]["10"], '"Second value"')

    def test_edit_form_resolve_text_preserves_paragraphs_and_direct_strings(self):
        html = make_edit_form_rehydration_html(
            [
                make_rehydration_text_entry("f", "First paragraph\nstill first\n\nSecond paragraph"),
                '10:"Quoted plain value"',
                '0:["$","$L1",null,{"modelStates":[]}]',
            ]
        )

        parsed = linkedin_cv._parse_edit_form_rehydration(html)

        self.assertEqual(
            linkedin_cv._edit_form_resolve_text(parsed, "$f"),
            "First paragraph still first\n\nSecond paragraph",
        )
        self.assertEqual(linkedin_cv._edit_form_resolve_text(parsed, "$10"), "Quoted plain value")
        self.assertEqual(linkedin_cv._edit_form_resolve_text(parsed, "Direct plain text"), "Direct plain text")
        self.assertEqual(linkedin_cv._edit_form_resolve_text(parsed, "$undefined"), "")

    def test_edit_form_resolve_text_repairs_obvious_split_word_wraps(self):
        html = make_edit_form_rehydration_html(
            [
                make_rehydration_text_entry(
                    "f",
                    "Sigma-compatible detection with co\nntext-aware evaluation\nrule\ns execute across profiles.",
                ),
                '0:["$","$L1",null,{"modelStates":[]}]',
            ]
        )

        parsed = linkedin_cv._parse_edit_form_rehydration(html)

        self.assertEqual(
            linkedin_cv._edit_form_resolve_text(parsed, "$f"),
            "Sigma-compatible detection with context-aware evaluation\nrules execute across profiles.",
        )

    def test_edit_form_resolve_text_ignores_non_text_payloads(self):
        html = make_edit_form_rehydration_html(
            [
                '1a:["$","div",null,{"children":["ignored"]}]',
                '0:["$","$L1",null,{"modelStates":[]}]',
            ]
        )

        parsed = linkedin_cv._parse_edit_form_rehydration(html)

        self.assertEqual(linkedin_cv._edit_form_resolve_text(parsed, "$1a"), "")

    def test_extract_initial_experience_pagination_request_from_como_html(self):
        pagination_request = linkedin_cv._extract_experience_initial_pagination_request_from_html(EXPERIENCE_COMO_HTML)

        self.assertIsNotNone(pagination_request)
        self.assertEqual(pagination_request["pagerId"], "com.linkedin.sdui.pagers.profile.details.experience")
        self.assertEqual(pagination_request["requestedArguments"]["payload"]["start"], 0)
        self.assertEqual(pagination_request["requestedArguments"]["payload"]["count"], 10)

    def test_extract_initial_certifications_pagination_request_from_como_html(self):
        pagination_request = linkedin_cv._extract_certifications_initial_pagination_request_from_html(CERTIFICATIONS_COMO_HTML)

        self.assertIsNotNone(pagination_request)
        self.assertEqual(pagination_request["pagerId"], "com.linkedin.sdui.pagers.profile.details.certifications")
        self.assertEqual(pagination_request["requestedArguments"]["payload"]["start"], 0)
        self.assertEqual(pagination_request["requestedArguments"]["payload"]["count"], 10)

    def test_extract_experience_records_from_rsc_text(self):
        experience = linkedin_cv._extract_experience_records_from_rsc_text(
            make_experience_rsc_response_text(
                [
                    {
                        "title": "Senior Security Engineer",
                        "company": "ExampleCo",
                        "company_url": "https://www.linkedin.com/company/1809/",
                        "employment_type": "Full-time",
                        "company_duration": "2 yrs 3 mos",
                        "company_location": "Berlin, Germany",
                        "date_range": "Jan 2023 - Present",
                        "duration": "2 yrs 3 mos",
                        "location": "Remote",
                        "description": "Built detection pipelines.\nAutomated incident response playbooks.",
                        "extra_line": "Principal engineer scope",
                    }
                ]
            )
        )

        self.assertEqual(
            experience,
            [
                {
                    "title": "Senior Security Engineer",
                    "company": "ExampleCo",
                    "company_url": "https://www.linkedin.com/company/1809/",
                    "employment_type": "Full-time",
                    "date_range": "Jan 2023 - Present",
                    "start_date_text": "Jan 2023",
                    "end_date_text": "Present",
                    "is_current": True,
                    "duration": "2 yrs 3 mos",
                    "location": "Remote",
                    "description": "Built detection pipelines.\nAutomated incident response playbooks.",
                    "raw_lines": ["Principal engineer scope"],
                }
            ],
        )

    def test_merge_education_record_from_edit_form_html(self):
        merged = linkedin_cv._merge_education_record(
            {
                "school": "Universidad Europea",
                "school_url": "https://www.linkedin.com/school/29216/",
                "degree": "Official Security Master's degree in Information and Communication Technologies",
                "field_of_study": "Security",
                "date_range": "2011 - 2012",
                "start_date_text": "2011",
                "end_date_text": "2012",
                "grade": "",
                "activities": "",
                "description": "",
                "raw_lines": [],
            },
            make_education_edit_form_html(
                school="Example University",
                degree="Official Security Master's degree in Information and Communication Technologies",
                field_of_study="Security",
                start_year=2011,
                end_year=2012,
                description="Thesis: 10,00",
                activities="Blue team research group",
                grade="9.8/10",
            ),
        )

        self.assertEqual(
            merged,
            {
                "school": "Example University",
                "school_url": "https://www.linkedin.com/school/29216/",
                "degree": "Official Security Master's degree in Information and Communication Technologies",
                "field_of_study": "Security",
                "date_range": "2011 - 2012",
                "start_date_text": "2011",
                "end_date_text": "2012",
                "grade": "9.8/10",
                "activities": "Blue team research group",
                "description": "Thesis: 10,00",
                "raw_lines": [],
            },
        )

    def test_merge_project_record_from_edit_form_html(self):
        merged = linkedin_cv._merge_project_record(
            {
                "name": "RedCurve — Local-First Endpoint Investigation Platform",
                "date_range": "Mar 2026 - Present",
                "start_date_text": "Mar 2026",
                "end_date_text": "Present",
                "is_current": True,
                "associated_with": "ExampleCo",
                "project_url": "",
                "description": "",
                "raw_lines": ["Visible in fraud lab"],
            },
            make_project_edit_form_html(
                name="RedCurve — Local-First Endpoint Investigation Platform",
                description="Node.js-based security analysis tool for investigating obfuscated JavaScript payloads.",
                project_url="https://example.com/redcurve",
                start_year=2026,
                start_month=3,
                end_year=0,
                end_month=0,
                currently_working=True,
            ),
        )

        self.assertEqual(
            merged,
            {
                "name": "RedCurve — Local-First Endpoint Investigation Platform",
                "date_range": "Mar 2026 - Present",
                "start_date_text": "Mar 2026",
                "end_date_text": "Present",
                "is_current": True,
                "associated_with": "ExampleCo",
                "project_url": "https://example.com/redcurve",
                "description": "Node.js-based security analysis tool for investigating obfuscated JavaScript payloads.",
                "raw_lines": [],
            },
        )

    def test_merge_project_record_drops_corrupted_rsc_blob_description(self):
        merged = linkedin_cv._merge_project_record(
            {
                "name": "Universal Crawler",
                "date_range": "Jan 2016 - Present",
                "start_date_text": "Jan 2016",
                "end_date_text": "Present",
                "is_current": True,
                "associated_with": "Bank of Ireland",
                "project_url": "",
                "description": "",
                "raw_lines": [],
            },
            make_project_edit_form_html_with_corrupted_description_ref(
                name="Universal Crawler",
                project_url="",
                start_year=2016,
                start_month=1,
                end_year=0,
                end_month=0,
                currently_working=True,
            ),
        )

        self.assertEqual(merged["name"], "Universal Crawler")
        self.assertEqual(merged["description"], "")
        self.assertEqual(merged["date_range"], "Jan 2016 - Present")

    def test_merge_experience_record_from_edit_form_html(self):
        merged = linkedin_cv._merge_experience_record(
            {
                "title": "Senior Security Engineer",
                "company": "ExampleCo",
                "company_url": "https://www.linkedin.com/company/1809/",
                "employment_type": "",
                "date_range": "",
                "start_date_text": "",
                "end_date_text": "",
                "is_current": False,
                "duration": "2 yrs 3 mos",
                "location": "",
                "description": "",
                "raw_lines": [],
            },
            make_experience_edit_form_html(
                title="Senior Security Engineer",
                company="ExampleCo",
                employment_type_value="12",
                start_year=2023,
                start_month=1,
                end_year=0,
                end_month=0,
                description="Built detection pipelines.\nAutomated incident response playbooks.",
                location="Remote",
                location_type="LocationType_REMOTE",
            ),
        )

        self.assertEqual(
            merged,
            {
                "title": "Senior Security Engineer",
                "company": "ExampleCo",
                "company_url": "https://www.linkedin.com/company/1809/",
                "employment_type": "Full-time",
                "date_range": "Jan 2023 - Present",
                "start_date_text": "Jan 2023",
                "end_date_text": "Present",
                "is_current": True,
                "duration": "2 yrs 3 mos",
                "location": "Remote",
                "description": "Built detection pipelines.\nAutomated incident response playbooks.",
                "raw_lines": [],
            },
        )

    def test_extract_license_records_from_rsc_text(self):
        licenses = linkedin_cv._extract_license_records_from_rsc_text(
            make_certifications_rsc_response_text(
                [
                    {
                        "name": "GIAC Certified Forensic Analyst (GCFA)",
                        "issuer": "GIAC",
                        "issue_date_text": "Jan 2024",
                        "expiration_date_text": "Jan 2028",
                        "credential_id": "ABC-123",
                        "credential_url": "https://example.com/verify",
                        "description": "Hands-on incident response certification.",
                    }
                ]
            )
        )

        self.assertEqual(
            licenses,
            [
                {
                    "name": "GIAC Certified Forensic Analyst (GCFA)",
                    "issuer": "GIAC",
                    "issue_date_text": "Jan 2024",
                    "expiration_date_text": "Jan 2028",
                    "credential_id": "ABC-123",
                    "credential_url": "https://example.com/verify",
                    "description": "Hands-on incident response certification.",
                    "raw_lines": [],
                }
            ],
        )

    def test_collect_network_responses_captures_skills_rsc_only(self):
        page = FakePage()
        captured = linkedin_cv._collect_json_network_responses(page)

        for callback in page.listeners["response"]:
            callback(
                FakeResponse(
                    url="https://www.linkedin.com/flagship-web/rsc-action/actions/pagination?sduiid=com.linkedin.sdui.pagers.profile.details.languages&parentSpanId=ignore-me",
                    text_value=UNRELATED_RSC_RESPONSE_TEXT,
                    content_type="text/x-component",
                )
            )
            callback(
                FakeResponse(
                    url="https://www.linkedin.com/flagship-web/rsc-action/actions/pagination?sduiid=com.linkedin.sdui.pagers.profile.details.skills&parentSpanId=volatile-span",
                    text_value=SKILLS_RSC_RESPONSE_TEXT,
                    content_type="text/x-component",
                )
            )

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["kind"], "skills_rsc")
        self.assertEqual(
            captured[0]["url"],
            "https://www.linkedin.com/flagship-web/rsc-action/actions/pagination?sduiid=com.linkedin.sdui.pagers.profile.details.skills",
        )

    def test_capture_uses_domcontentloaded_and_no_ui_mutation(self):
        page = FakePage()
        context = FakeContext(page)
        app_home = tempfile.mkdtemp()
        write_session_state(app_home, "personal")
        manager = FakePlaywrightManager(context)

        result = linkedin_cv.capture_accessible_profile(
            profile_name="personal",
            profile_id="demo-profile",
            confirm_accessible_profile_capture=True,
            app_home=app_home,
            playwright_factory=lambda: manager,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(page.goto_calls[0][1], "domcontentloaded")
        self.assertEqual(page.disallowed_clicks, [])
        self.assertEqual(result["result"]["capture_type"], "accessible_profile")
        self.assertEqual(result["result"]["status"], "ok")

    def test_capture_own_profile_requires_saved_session_state(self):
        page = FakePage(html=OWN_PROFILE_HTML)
        context = FakeContext(page)

        result = linkedin_cv.capture_own_profile(
            profile_name="personal",
            app_home=tempfile.mkdtemp(),
            playwright_factory=lambda: FakePlaywrightManager(context),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["result"]["status"], "missing_session")
        self.assertIn("uv run agent-toolbelt-linkedin-cv session login --profile personal", result["stderr"])

    def test_capture_accessible_profile_requires_saved_session_state(self):
        page = FakePage(html=PUBLIC_PROFILE_HTML)
        context = FakeContext(page)

        result = linkedin_cv.capture_accessible_profile(
            profile_name="personal",
            profile_id="demo-profile",
            confirm_accessible_profile_capture=True,
            app_home=tempfile.mkdtemp(),
            playwright_factory=lambda: FakePlaywrightManager(context),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["result"]["status"], "missing_session")
        self.assertIn("uv run agent-toolbelt-linkedin-cv session login --profile personal", result["stderr"])

    def test_deep_own_capture_uses_rsc_skills_when_skills_dom_is_empty(self):
        page = SkillsRscDeepFakePage()
        context = FakeContext(page)
        app_home = tempfile.mkdtemp()
        write_session_state(app_home, "personal")

        def fake_request_with_session(*, url: str, method: str = "GET", payload=None, **_kwargs):
            if method == "GET":
                if url.endswith("/details/skills/"):
                    return 200, url, SKILLS_COMO_HTML
                if url.endswith("/details/education/"):
                    return 200, url, EDUCATION_COMO_HTML
                if url.endswith("/details/experience/") or url.endswith("/details/certifications/"):
                    return 200, url, "<html><body><main><div>Section</div></main></body></html>"
                raise AssertionError(url)
            pager_id = payload["paginationRequest"]["pagerId"]
            if pager_id == "com.linkedin.sdui.pagers.profile.details.education":
                self.assertEqual(payload["paginationRequest"]["requestedArguments"]["payload"]["start"], 0)
                return 200, url, make_education_rsc_response_text([])
            start = payload["paginationRequest"]["requestedArguments"]["payload"]["start"]
            self.assertEqual(start, 0)
            return 200, url, SKILLS_RSC_RESPONSE_TEXT

        with patch.object(linkedin_cv, "_request_with_session", side_effect=fake_request_with_session):
            result = linkedin_cv.capture_own_profile(
                profile_name="personal",
                app_home=app_home,
                playwright_factory=lambda: FakePlaywrightManager(context),
            )

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["result"]["skills"],
            [
                "Software Architecture",
                "Systems Programming",
                "Rust (Programming Language)",
                "Event Tracing for Windows (ETW)",
                "SIGMA Rules",
            ],
        )
        self.assertEqual(result["result"]["section_sources"]["skills"], "network")
        self.assertEqual(result["result"]["section_transport"]["skills"], "api_replay")
        self.assertIn("https://www.linkedin.com/in/alex-candidate/details/skills/", result["result"]["detail_routes_visited"])
        self.assertEqual(
            result["result"]["network_responses_used"],
            ["https://www.linkedin.com/flagship-web/rsc-action/actions/pagination?sduiid=com.linkedin.sdui.pagers.profile.details.skills"],
        )
        self.assertFalse(any("/details/skills/" in url for url, *_ in page.goto_calls))
        self.assertEqual(page.evaluate_calls, [])

    def test_capture_languages_route_replays_request_only(self):
        app_home = tempfile.mkdtemp()
        state_path = write_session_state(app_home, "personal")
        calls: list[tuple[str, str]] = []

        def fake_request_with_session(*, url: str, method: str = "GET", payload=None, **_kwargs):
            if method == "GET":
                calls.append(("GET", url))
                return 200, url, LANGUAGES_COMO_HTML
            calls.append(("POST", url))
            self.assertEqual(payload["paginationRequest"]["requestedArguments"]["payload"]["start"], 0)
            return 200, url, make_languages_rsc_response_text(
                [
                    ("Francés", "Limited working proficiency"),
                    ("Inglés", "Full professional proficiency"),
                    ("Italiano", "Elementary proficiency"),
                ]
            )

        with patch.object(linkedin_cv, "_request_with_session", side_effect=fake_request_with_session):
            languages, blocker, records = linkedin_cv._capture_languages_route(
                state_path=state_path,
                route_url="https://www.linkedin.com/in/alex-candidate/details/languages/",
                timeout_sec=5,
            )

        self.assertEqual(
            languages,
            [
                "Francés - Limited working proficiency",
                "Inglés - Full professional proficiency",
                "Italiano - Elementary proficiency",
            ],
        )
        self.assertIsNone(blocker)
        self.assertEqual(
            calls,
            [
                ("GET", "https://www.linkedin.com/in/alex-candidate/details/languages/"),
                ("POST", "https://www.linkedin.com/flagship-web/rsc-action/actions/pagination?sduiid=com.linkedin.sdui.pagers.profile.details.languages"),
            ],
        )
        self.assertEqual(len(records), 1)

    def test_capture_skills_route_replays_requests_only_until_expected_count(self):
        app_home = tempfile.mkdtemp()
        state_path = write_session_state(app_home, "personal")
        calls: list[tuple[str, int | None]] = []

        def fake_request_with_session(*, url: str, method: str = "GET", payload=None, **_kwargs):
            if method == "GET":
                calls.append(("GET", None))
                return 200, url, SKILLS_COMO_HTML
            start = payload["paginationRequest"]["requestedArguments"]["payload"]["start"]
            calls.append(("POST", start))
            responses = {
                0: make_skills_rsc_response_text([f"Skill {index}" for index in range(1, 11)], next_start=10),
                10: make_skills_rsc_response_text([f"Skill {index}" for index in range(11, 21)], next_start=20),
                20: make_skills_rsc_response_text([f"Skill {index}" for index in range(21, 31)], next_start=30),
            }
            return 200, url, responses[start]

        with patch.object(linkedin_cv, "_request_with_session", side_effect=fake_request_with_session):
            skills, blocker, records = linkedin_cv._capture_skills_route(
                state_path=state_path,
                route_url="https://www.linkedin.com/in/alex-candidate/details/skills/",
                timeout_sec=5,
                expected_count=30,
            )

        self.assertEqual(len(skills), 30)
        self.assertEqual(skills[0], "Skill 1")
        self.assertEqual(skills[-1], "Skill 30")
        self.assertIsNone(blocker)
        self.assertEqual(calls, [("GET", None), ("POST", 0), ("POST", 10), ("POST", 20)])
        self.assertEqual(len(records), 3)

    def test_capture_education_route_replays_requests_only_until_exhausted(self):
        app_home = tempfile.mkdtemp()
        state_path = write_session_state(app_home, "personal")
        calls: list[tuple[str, str | int | None]] = []

        def fake_request_with_session(*, url: str, method: str = "GET", payload=None, **_kwargs):
            if method == "GET" and url.endswith("/details/education/"):
                calls.append(("GET", "route"))
                return 200, url, EDUCATION_COMO_HTML
            if method == "GET" and "/details/education/edit/forms/" in url:
                form_id = url.rstrip("/").split("/")[-1]
                calls.append(("GET", form_id))
                forms = {
                    "1": make_education_edit_form_html(
                        school="Example University",
                        degree="Official Security Master's degree in Information and Communication Technologies",
                        field_of_study="Security",
                        start_year=2011,
                        end_year=2012,
                        description="Thesis: 10,00",
                        activities="Blue team research group",
                        grade="9.8/10",
                    ),
                    "2": make_education_edit_form_html(
                        school="Universidad Complutense de Madrid",
                        degree="Bachelor of Science",
                        field_of_study="Computer Science",
                        start_year=2007,
                        end_year=2011,
                        description="Systems and software engineering track.",
                        activities="Programming club",
                        grade="8.7/10",
                    ),
                }
                return 200, url, forms[form_id]
            start = payload["paginationRequest"]["requestedArguments"]["payload"]["start"]
            calls.append(("POST", start))
            responses = {
                0: make_education_rsc_response_text(
                    [
                        {
                            "edit_form_id": 1,
                            "school": "Universidad Europea",
                            "school_url": "https://www.linkedin.com/school/29216/",
                            "degree": "Official Security Master's degree in Information and Communication Technologies",
                            "field_of_study": "Security",
                            "date_range": "2011 - 2012",
                            "raw_lines": ["Thesis: Malware traffic classification"],
                        }
                    ],
                    next_start=10,
                ),
                10: make_education_rsc_response_text(
                    [
                        {
                            "edit_form_id": 2,
                            "school": "Universidad Complutense",
                            "school_url": "https://www.linkedin.com/school/28731/",
                            "degree": "Bachelor of Science",
                            "field_of_study": "Computer Science",
                            "date_range": "2007 - 2011",
                        }
                    ]
                ),
            }
            return 200, url, responses[start]

        with patch.object(linkedin_cv, "_request_with_session", side_effect=fake_request_with_session):
            education, blocker, records = linkedin_cv._capture_education_route(
                state_path=state_path,
                route_url="https://www.linkedin.com/in/alex-candidate/details/education/",
                timeout_sec=5,
            )

        self.assertEqual(len(education), 2)
        self.assertEqual(education[0]["school"], "Example University")
        self.assertEqual(education[0]["description"], "Thesis: 10,00")
        self.assertEqual(education[0]["activities"], "Blue team research group")
        self.assertEqual(education[1]["school"], "Universidad Complutense de Madrid")
        self.assertEqual(education[1]["grade"], "8.7/10")
        self.assertIsNone(blocker)
        self.assertEqual(calls, [("GET", "route"), ("POST", 0), ("GET", "1"), ("POST", 10), ("GET", "2")])
        self.assertEqual(len(records), 2)

    def test_capture_projects_route_replays_requests_only_until_exhausted(self):
        app_home = tempfile.mkdtemp()
        state_path = write_session_state(app_home, "personal")
        calls: list[tuple[str, str | int | None]] = []

        def fake_request_with_session(*, url: str, method: str = "GET", payload=None, **_kwargs):
            if method == "GET" and url.endswith("/details/projects/"):
                calls.append(("GET", "route"))
                return 200, url, PROJECTS_COMO_HTML
            if method == "GET" and "/details/projects/edit/forms/" in url:
                form_id = url.rstrip("/").split("/")[-1]
                calls.append(("GET", form_id))
                forms = {
                    "1": make_project_edit_form_html(
                        name="RedCurve — Local-First Endpoint Investigation Platform",
                        description="Node.js-based security analysis tool for investigating obfuscated JavaScript payloads.",
                        project_url="https://example.com/redcurve",
                        start_year=2026,
                        start_month=3,
                        end_year=0,
                        end_month=0,
                        currently_working=True,
                    ),
                    "2": make_project_edit_form_html(
                        name="Splunk–XSOAR End-to-End Orchestration Pipeline",
                        description="Full end-to-end SOAR integration pipeline for MDR alert processing.",
                        project_url="",
                        start_year=2024,
                        start_month=0,
                        end_year=0,
                        end_month=0,
                        currently_working=True,
                    ),
                }
                return 200, url, forms[form_id]
            start = payload["paginationRequest"]["requestedArguments"]["payload"]["start"]
            calls.append(("POST", start))
            responses = {
                0: make_projects_rsc_response_text(
                    [
                        {
                            "edit_form_id": 1,
                            "name": "RedCurve — Local-First Endpoint Investigation Platform",
                            "date_range": "Mar 2026 - Present",
                            "associated_with": "ExampleCo",
                        }
                    ],
                    next_start=10,
                ),
                10: make_projects_rsc_response_text(
                    [
                        {
                            "edit_form_id": 2,
                            "name": "Splunk–XSOAR End-to-End Orchestration Pipeline",
                            "date_range": "2024 - Present",
                            "associated_with": "ExampleCo",
                        }
                    ]
                ),
            }
            return 200, url, responses[start]

        with patch.object(linkedin_cv, "_request_with_session", side_effect=fake_request_with_session):
            projects, blocker, records = linkedin_cv._capture_projects_route(
                state_path=state_path,
                route_url="https://www.linkedin.com/in/alex-candidate/details/projects/",
                timeout_sec=5,
            )

        self.assertEqual(len(projects), 2)
        self.assertEqual(projects[0]["name"], "RedCurve — Local-First Endpoint Investigation Platform")
        self.assertEqual(projects[0]["associated_with"], "ExampleCo")
        self.assertEqual(projects[0]["project_url"], "https://example.com/redcurve")
        self.assertEqual(projects[1]["description"], "Full end-to-end SOAR integration pipeline for MDR alert processing.")
        self.assertIsNone(blocker)
        self.assertEqual(calls, [("GET", "route"), ("POST", 0), ("GET", "1"), ("POST", 10), ("GET", "2")])
        self.assertEqual(len(records), 2)

    def test_capture_experience_route_replays_requests_only_until_exhausted(self):
        app_home = tempfile.mkdtemp()
        state_path = write_session_state(app_home, "personal")
        calls: list[tuple[str, str | int | None]] = []

        def fake_request_with_session(*, url: str, method: str = "GET", payload=None, **_kwargs):
            if method == "GET" and url.endswith("/details/experience/"):
                calls.append(("GET", "route"))
                return 200, url, EXPERIENCE_COMO_HTML
            if method == "GET" and "/details/experience/edit/forms/" in url:
                form_id = url.rstrip("/").split("/")[-1]
                calls.append(("GET", form_id))
                forms = {
                    "1": make_experience_edit_form_html(
                        title="Senior Security Engineer",
                        company="ExampleCo",
                        employment_type_value="12",
                        start_year=2023,
                        start_month=1,
                        end_year=0,
                        end_month=0,
                        description="Built detection pipelines.\nAutomated incident response playbooks.",
                        location="Remote",
                        location_type="LocationType_REMOTE",
                    ),
                    "2": make_experience_edit_form_html(
                        title="Incident Response Lead",
                        company="PreviousCo",
                        employment_type_value="2",
                        start_year=2021,
                        start_month=6,
                        end_year=2022,
                        end_month=12,
                        description="Led investigations and containment.",
                        location="Berlin, Germany",
                    ),
                }
                return 200, url, forms[form_id]
            start = payload["paginationRequest"]["requestedArguments"]["payload"]["start"]
            calls.append(("POST", start))
            responses = {
                0: make_experience_rsc_response_text(
                    [
                        {
                            "title": "Senior Security Engineer",
                            "company": "ExampleCo",
                            "company_url": "https://www.linkedin.com/company/1809/",
                            "employment_type": "Full-time",
                            "company_duration": "2 yrs 3 mos",
                            "company_location": "Berlin, Germany",
                            "date_range": "Jan 2023 - Present",
                            "duration": "2 yrs 3 mos",
                            "location": "Remote",
                            "description": "Built detection pipelines.",
                        }
                    ],
                    next_start=10,
                ),
                10: make_experience_rsc_response_text(
                    [
                        {
                            "title": "Incident Response Lead",
                            "company": "PreviousCo",
                            "company_url": "https://www.linkedin.com/company/1810/",
                            "employment_type": "Contract",
                            "company_duration": "1 yr 6 mos",
                            "date_range": "Jun 2021 - Dec 2022",
                            "duration": "1 yr 6 mos",
                            "location": "Berlin, Germany",
                            "description": "Led investigations and containment.",
                        }
                    ]
                ),
            }
            return 200, url, responses[start]

        with patch.object(linkedin_cv, "_request_with_session", side_effect=fake_request_with_session):
            experience, blocker, records = linkedin_cv._capture_experience_route(
                state_path=state_path,
                route_url="https://www.linkedin.com/in/alex-candidate/details/experience/",
                timeout_sec=5,
            )

        self.assertEqual(len(experience), 2)
        self.assertEqual(experience[0]["title"], "Senior Security Engineer")
        self.assertEqual(experience[1]["company"], "PreviousCo")
        self.assertEqual(
            experience[0]["description"],
            "Built detection pipelines.\nAutomated incident response playbooks.",
        )
        self.assertEqual(experience[1]["employment_type"], "Contract")
        self.assertIsNone(blocker)
        self.assertEqual(calls, [("GET", "route"), ("POST", 0), ("GET", "1"), ("POST", 10)])
        self.assertEqual(len(records), 2)

    def test_capture_licenses_route_returns_empty_without_blocker(self):
        app_home = tempfile.mkdtemp()
        state_path = write_session_state(app_home, "personal")
        calls: list[tuple[str, int | None]] = []

        def fake_request_with_session(*, url: str, method: str = "GET", payload=None, **_kwargs):
            if method == "GET":
                calls.append(("GET", None))
                return 200, url, CERTIFICATIONS_COMO_HTML
            start = payload["paginationRequest"]["requestedArguments"]["payload"]["start"]
            calls.append(("POST", start))
            return 200, url, make_certifications_rsc_response_text([])

        with patch.object(linkedin_cv, "_request_with_session", side_effect=fake_request_with_session):
            licenses, blocker, records = linkedin_cv._capture_licenses_route(
                state_path=state_path,
                route_url="https://www.linkedin.com/in/alex-candidate/details/certifications/",
                timeout_sec=5,
            )

        self.assertEqual(licenses, [])
        self.assertIsNone(blocker)
        self.assertEqual(calls, [("GET", None), ("POST", 0)])
        self.assertEqual(len(records), 1)

    def test_deep_own_capture_keeps_paginating_skills_until_expected_count(self):
        page = SkillsCountRscDeepFakePage()
        context = FakeContext(page)
        manager = FakePlaywrightManager(context)
        app_home = tempfile.mkdtemp()
        write_session_state(app_home, "personal")

        def fake_request_with_session(*, url: str, method: str = "GET", payload=None, **_kwargs):
            if method == "GET":
                return 200, url, SKILLS_COMO_HTML
            start = payload["paginationRequest"]["requestedArguments"]["payload"]["start"]
            responses = {
                0: make_skills_rsc_response_text([f"Skill {index}" for index in range(1, 11)], next_start=10),
                10: make_skills_rsc_response_text([f"Skill {index}" for index in range(11, 21)], next_start=20),
                20: make_skills_rsc_response_text([f"Skill {index}" for index in range(21, 26)]),
            }
            return 200, url, responses[start]

        with patch.object(linkedin_cv, "_request_with_session", side_effect=fake_request_with_session):
            result = linkedin_cv.capture_own_profile(
                profile_name="personal",
                app_home=app_home,
                playwright_factory=lambda: manager,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(len(result["result"]["skills"]), 25)
        self.assertEqual(result["result"]["skills"][0], "Skill 1")
        self.assertEqual(result["result"]["skills"][-1], "Skill 25")
        self.assertEqual(result["result"]["section_transport"]["skills"], "api_replay")
        self.assertNotIn("skills", result["result"]["section_blockers"])
        self.assertEqual(page.evaluate_calls, [])
        self.assertFalse(any("/details/skills/" in url for url, *_ in page.goto_calls))
        self.assertTrue(manager.playwright.chromium.launch_args)
        _, kwargs = manager.playwright.chromium.launch_args[0]
        self.assertTrue(kwargs.get("headless"))

    def test_deep_own_capture_sets_blocker_when_skills_pagination_stops_early(self):
        page = SkillsEarlyStopRscDeepFakePage()
        context = FakeContext(page)
        app_home = tempfile.mkdtemp()
        write_session_state(app_home, "personal")

        def fake_request_with_session(*, url: str, method: str = "GET", payload=None, **_kwargs):
            if method == "GET":
                return 200, url, SKILLS_COMO_HTML
            start = payload["paginationRequest"]["requestedArguments"]["payload"]["start"]
            self.assertEqual(start, 0)
            return 200, url, make_skills_rsc_response_text([f"Skill {index}" for index in range(1, 11)])

        with patch.object(linkedin_cv, "_request_with_session", side_effect=fake_request_with_session):
            result = linkedin_cv.capture_own_profile(
                profile_name="personal",
                app_home=app_home,
                playwright_factory=lambda: FakePlaywrightManager(context),
            )

        self.assertTrue(result["ok"])
        self.assertEqual(len(result["result"]["skills"]), 10)
        self.assertEqual(result["result"]["skills"][0], "Skill 1")
        self.assertEqual(result["result"]["skills"][-1], "Skill 10")
        self.assertEqual(result["result"]["section_blockers"]["skills"], "pagination_stopped_early")

    def test_deep_own_capture_uses_rsc_languages_when_languages_dom_is_empty(self):
        page = LanguagesRouteDeepFakePage()
        context = FakeContext(page)
        app_home = tempfile.mkdtemp()
        write_session_state(app_home, "personal")

        def fake_request_with_session(*, url: str, method: str = "GET", payload=None, **_kwargs):
            if method == "GET":
                if url.endswith("/details/languages/"):
                    return 200, url, LANGUAGES_COMO_HTML
                if url.endswith("/details/education/"):
                    return 200, url, EDUCATION_COMO_HTML
                if url.endswith("/details/skills/"):
                    return 200, url, "<html><body><main><div>Skills</div></main></body></html>"
                if url.endswith("/details/experience/") or url.endswith("/details/certifications/"):
                    return 200, url, "<html><body><main><div>Section</div></main></body></html>"
                raise AssertionError(url)
            pager_id = payload["paginationRequest"]["pagerId"]
            if pager_id == "com.linkedin.sdui.pagers.profile.details.education":
                self.assertEqual(payload["paginationRequest"]["requestedArguments"]["payload"]["start"], 0)
                return 200, url, make_education_rsc_response_text([])
            if pager_id == "com.linkedin.sdui.pagers.profile.details.languages":
                self.assertEqual(payload["paginationRequest"]["requestedArguments"]["payload"]["start"], 0)
                return 200, url, make_languages_rsc_response_text(
                    [
                        ("Francés", "Limited working proficiency"),
                        ("Inglés", "Full professional proficiency"),
                    ]
                )
            raise AssertionError(pager_id)

        with patch.object(linkedin_cv, "_request_with_session", side_effect=fake_request_with_session):
            result = linkedin_cv.capture_own_profile(
                profile_name="personal",
                app_home=app_home,
                playwright_factory=lambda: FakePlaywrightManager(context),
            )

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["result"]["languages"],
            [
                "Francés - Limited working proficiency",
                "Inglés - Full professional proficiency",
            ],
        )
        self.assertEqual(result["result"]["section_sources"]["languages"], "network")
        self.assertEqual(result["result"]["section_transport"]["languages"], "api_replay")
        self.assertIn("https://www.linkedin.com/in/alex-candidate/details/languages/", result["result"]["detail_routes_visited"])
        self.assertEqual(
            result["result"]["network_responses_used"],
            ["https://www.linkedin.com/flagship-web/rsc-action/actions/pagination?sduiid=com.linkedin.sdui.pagers.profile.details.languages"],
        )
        self.assertFalse(any("/details/languages/" in url for url, *_ in page.goto_calls))
        self.assertEqual(page.evaluate_calls, [])

    def test_deep_own_capture_uses_request_only_education_experience_and_empty_licenses(self):
        page = ConstructedRouteDeepFakePage()
        context = FakeContext(page)
        app_home = tempfile.mkdtemp()
        write_session_state(app_home, "personal")

        def fake_request_with_session(*, url: str, method: str = "GET", payload=None, **_kwargs):
            if method == "GET":
                if url.endswith("/details/education/"):
                    return 200, url, EDUCATION_COMO_HTML
                if "/details/education/edit/forms/" in url:
                    return 200, url, make_education_edit_form_html(
                        school="Example University",
                        degree="Official Security Master's degree in Information and Communication Technologies",
                        field_of_study="Security",
                        start_year=2011,
                        end_year=2012,
                        description="Thesis: 10,00",
                        activities="Blue team research group",
                        grade="9.8/10",
                    )
                if url.endswith("/details/experience/"):
                    return 200, url, EXPERIENCE_COMO_HTML
                if url.endswith("/details/certifications/"):
                    return 200, url, CERTIFICATIONS_COMO_HTML
                if "/details/experience/edit/forms/" in url:
                    return 200, url, make_experience_edit_form_html(
                        title="Senior Security Engineer",
                        company="ExampleCo",
                        employment_type_value="12",
                        start_year=2023,
                        start_month=1,
                        end_year=0,
                        end_month=0,
                        description="Built detection pipelines.\nAutomated incident response playbooks.",
                        location="Remote",
                        location_type="LocationType_REMOTE",
                    )
                if url.endswith("/details/skills/"):
                    return 200, url, "<html><body><main><div>Skills</div></main></body></html>"
                raise AssertionError(url)
            pager_id = payload["paginationRequest"]["pagerId"]
            start = payload["paginationRequest"]["requestedArguments"]["payload"]["start"]
            if pager_id == "com.linkedin.sdui.pagers.profile.details.education":
                self.assertEqual(start, 0)
                return 200, url, make_education_rsc_response_text(
                    [
                        {
                            "edit_form_id": 1,
                            "school": "Universidad Europea",
                            "school_url": "https://www.linkedin.com/school/29216/",
                            "degree": "Official Security Master's degree in Information and Communication Technologies",
                            "field_of_study": "Security",
                            "date_range": "2011 - 2012",
                        }
                    ]
                )
            if pager_id == "com.linkedin.sdui.pagers.profile.details.experience":
                self.assertEqual(start, 0)
                return 200, url, make_experience_rsc_response_text(
                    [
                        {
                            "title": "Senior Security Engineer",
                            "company": "ExampleCo",
                            "company_url": "https://www.linkedin.com/company/1809/",
                            "employment_type": "Full-time",
                            "company_duration": "2 yrs 3 mos",
                            "company_location": "Berlin, Germany",
                            "date_range": "Jan 2023 - Present",
                            "duration": "2 yrs 3 mos",
                            "location": "Remote",
                            "description": "Built detection pipelines.",
                        }
                    ]
                )
            if pager_id == "com.linkedin.sdui.pagers.profile.details.certifications":
                self.assertEqual(start, 0)
                return 200, url, make_certifications_rsc_response_text([])
            raise AssertionError(pager_id)

        with patch.object(linkedin_cv, "_request_with_session", side_effect=fake_request_with_session):
            result = linkedin_cv.capture_own_profile(
                profile_name="personal",
                app_home=app_home,
                playwright_factory=lambda: FakePlaywrightManager(context),
            )

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["result"]["education"],
            [
                {
                    "school": "Example University",
                    "school_url": "https://www.linkedin.com/school/29216/",
                    "degree": "Official Security Master's degree in Information and Communication Technologies",
                    "field_of_study": "Security",
                    "date_range": "2011 - 2012",
                    "start_date_text": "2011",
                    "end_date_text": "2012",
                    "grade": "9.8/10",
                    "activities": "Blue team research group",
                    "description": "Thesis: 10,00",
                    "raw_lines": [],
                }
            ],
        )
        self.assertEqual(
            result["result"]["experience"],
            [
                {
                    "title": "Senior Security Engineer",
                    "company": "ExampleCo",
                    "company_url": "https://www.linkedin.com/company/1809/",
                    "employment_type": "Full-time",
                    "date_range": "Jan 2023 - Present",
                    "start_date_text": "Jan 2023",
                    "end_date_text": "Present",
                    "is_current": True,
                    "duration": "2 yrs 3 mos",
                    "location": "Remote",
                    "description": "Built detection pipelines.\nAutomated incident response playbooks.",
                    "raw_lines": [],
                }
            ],
        )
        self.assertEqual(result["result"]["licenses_certifications"], [])
        self.assertEqual(result["result"]["section_transport"]["education"], "api_replay")
        self.assertEqual(result["result"]["section_transport"]["experience"], "api_replay")
        self.assertEqual(result["result"]["section_transport"]["licenses_certifications"], "api_replay")
        self.assertNotIn("licenses_certifications", result["result"]["section_blockers"])
        self.assertFalse(any("/details/education/" in url for url, *_ in page.goto_calls))
        self.assertFalse(any("/details/experience/" in url for url, *_ in page.goto_calls))
        self.assertFalse(any("/details/certifications/" in url for url, *_ in page.goto_calls))

    def test_own_capture_save_raw_sanitizes_skills_rsc_records(self):
        page = SkillsRscDeepFakePage()
        context = FakeContext(page)
        app_home = tempfile.mkdtemp()
        write_session_state(app_home, "personal")

        def fake_request_with_session(*, url: str, method: str = "GET", payload=None, **_kwargs):
            if method == "GET":
                return 200, url, SKILLS_COMO_HTML
            return 200, url, SKILLS_RSC_RESPONSE_TEXT

        with patch.object(linkedin_cv, "_request_with_session", side_effect=fake_request_with_session):
            result = linkedin_cv.capture_own_profile(
                profile_name="personal",
                app_home=app_home,
                save_raw=True,
                playwright_factory=lambda: FakePlaywrightManager(context),
            )

        self.assertTrue(result["ok"])
        saved_payloads = json.loads(Path(result["result"]["raw_network_path"]).read_text(encoding="utf-8"))
        self.assertEqual(
            saved_payloads[0]["url"],
            "https://www.linkedin.com/flagship-web/rsc-action/actions/pagination?sduiid=com.linkedin.sdui.pagers.profile.details.skills",
        )
        self.assertEqual(saved_payloads[0]["kind"], "skills_rsc")
        self.assertIn("Software Architecture", saved_payloads[0]["body"])
        self.assertNotIn("parentSpanId", saved_payloads[0]["url"])

    def test_compare_snapshots_handles_structured_experience_and_licenses(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            own_path = Path(temp_dir) / "own.json"
            target_path = Path(temp_dir) / "target.json"
            own_path.write_text(
                json.dumps(
                    {
                        "name": "Alex Candidate",
                        "headline": "Security engineer",
                        "about": "",
                        "experience": [],
                        "licenses_certifications": [],
                        "skills": ["Python"],
                    }
                ),
                encoding="utf-8",
            )
            target_path.write_text(
                json.dumps(
                    {
                        "name": "Jane Candidate",
                        "headline": "Senior Detection Engineer helping SaaS teams reduce alert fatigue",
                        "about": "Builds threat detection programs with measurable incident outcomes.",
                        "experience": [
                            {
                                "title": "Lead Security Engineer",
                                "company": "ExampleCo",
                                "date_range": "2021 - Present",
                                "description": "Owns detection engineering and response automation across SaaS environments.",
                            }
                        ],
                        "licenses_certifications": [
                            {
                                "name": "GCFA",
                                "issuer": "GIAC",
                                "description": "Forensics certification.",
                            }
                        ],
                        "skills": ["Detection Engineering", "Python", "SIEM"],
                    }
                ),
                encoding="utf-8",
            )

            result = linkedin_cv.compare_snapshots(own_snapshot=str(own_path), target_snapshot=str(target_path))

        self.assertTrue(result["ok"])
        self.assertIn("experience", result["result"]["missing_or_thin_sections"])
        self.assertIn("licenses_certifications", result["result"]["missing_or_thin_sections"])
        self.assertIn("Add quantified responsibility and impact bullets to experience entries.", result["result"]["improvement_areas"])

    def test_own_capture_records_final_redirected_profile_url(self):
        page = RedirectingFakePage(html=OWN_PROFILE_HTML)
        context = FakeContext(page)
        app_home = tempfile.mkdtemp()
        write_session_state(app_home, "personal")

        result = linkedin_cv.capture_own_profile(
            profile_name="personal",
            app_home=app_home,
            playwright_factory=lambda: FakePlaywrightManager(context),
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["profile_id"], "alex-candidate")
        self.assertEqual(result["result"]["profile_url"], "https://www.linkedin.com/in/alex-candidate/")

    def test_accessible_capture_uses_saved_session_and_headless_context(self):
        page = FakePage(html=PUBLIC_PROFILE_HTML)
        context = FakeContext(page)
        manager = FakePlaywrightManager(context)
        app_home = tempfile.mkdtemp()
        write_session_state(app_home, "personal")

        result = linkedin_cv.capture_accessible_profile(
            profile_name="personal",
            profile_id="demo-profile",
            confirm_accessible_profile_capture=True,
            app_home=app_home,
            playwright_factory=lambda: manager,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["capture_type"], "accessible_profile")
        self.assertTrue(manager.playwright.chromium.launch_args)
        _, kwargs = manager.playwright.chromium.launch_args[0]
        self.assertTrue(kwargs.get("headless"))

    def test_accessible_capture_handles_transient_page_content_navigation_and_uses_request_only_sections(self):
        page = FlakyContentAccessiblePage()
        context = FakeContext(page)
        app_home = tempfile.mkdtemp()
        write_session_state(app_home, "personal")

        def fake_request_with_session(*, url: str, method: str = "GET", payload=None, **_kwargs):
            if method == "GET":
                if url.endswith("/details/skills/"):
                    return 200, url, SKILLS_COMO_HTML
                if url.endswith("/details/education/"):
                    return 200, url, EDUCATION_COMO_HTML
                if url.endswith("/details/experience/"):
                    return 200, url, EXPERIENCE_COMO_HTML
                if url.endswith("/details/certifications/"):
                    return 200, url, CERTIFICATIONS_COMO_HTML
                if "/details/experience/edit/forms/" in url:
                    return 200, url, make_experience_edit_form_html(
                        title="Senior Security Engineer",
                        company="ExampleCo",
                        employment_type_value="12",
                        start_year=2023,
                        start_month=1,
                        end_year=0,
                        end_month=0,
                        description="Built detection pipelines.\nAutomated incident response playbooks.",
                        location="Remote",
                        location_type="LocationType_REMOTE",
                    )
                raise AssertionError(url)
            pager_id = payload["paginationRequest"]["pagerId"]
            start = payload["paginationRequest"]["requestedArguments"]["payload"]["start"]
            if pager_id == "com.linkedin.sdui.pagers.profile.details.skills":
                self.assertEqual(start, 0)
                return 200, url, make_skills_rsc_response_text(["Skill 1", "Skill 2"])
            if pager_id == "com.linkedin.sdui.pagers.profile.details.education":
                self.assertEqual(start, 0)
                return 200, url, make_education_rsc_response_text([])
            if pager_id == "com.linkedin.sdui.pagers.profile.details.experience":
                self.assertEqual(start, 0)
                return 200, url, make_experience_rsc_response_text(
                    [
                        {
                            "title": "Senior Security Engineer",
                            "company": "ExampleCo",
                            "company_url": "https://www.linkedin.com/company/1809/",
                            "employment_type": "Full-time",
                            "company_duration": "2 yrs 3 mos",
                            "company_location": "Berlin, Germany",
                            "date_range": "Jan 2023 - Present",
                            "duration": "2 yrs 3 mos",
                            "location": "Remote",
                            "description": "Built detection pipelines.",
                        }
                    ]
                )
            if pager_id == "com.linkedin.sdui.pagers.profile.details.certifications":
                self.assertEqual(start, 0)
                return 200, url, make_certifications_rsc_response_text([])
            raise AssertionError(pager_id)

        with patch.object(linkedin_cv, "_request_with_session", side_effect=fake_request_with_session):
            result = linkedin_cv.capture_accessible_profile(
                profile_name="personal",
                url="https://www.linkedin.com/in/demo-profile/",
                confirm_accessible_profile_capture=True,
                app_home=app_home,
                playwright_factory=lambda: FakePlaywrightManager(context),
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["capture_type"], "accessible_profile")
        self.assertEqual(result["result"]["status"], "ok")
        self.assertEqual(result["result"]["profile_url"], "https://www.linkedin.com/in/demo-profile/")
        self.assertEqual(result["result"]["skills"], ["Skill 1", "Skill 2"])
        self.assertEqual(
            result["result"]["experience"],
            [
                {
                    "title": "Senior Security Engineer",
                    "company": "ExampleCo",
                    "company_url": "https://www.linkedin.com/company/1809/",
                    "employment_type": "Full-time",
                    "date_range": "Jan 2023 - Present",
                    "start_date_text": "Jan 2023",
                    "end_date_text": "Present",
                    "is_current": True,
                    "duration": "2 yrs 3 mos",
                    "location": "Remote",
                    "description": "Built detection pipelines.\nAutomated incident response playbooks.",
                    "raw_lines": [],
                }
            ],
        )
        self.assertEqual(result["result"]["licenses_certifications"], [])
        self.assertEqual(result["result"]["section_transport"]["skills"], "api_replay")
        self.assertEqual(result["result"]["section_transport"]["experience"], "api_replay")

    def test_accessible_capture_parses_request_only_sections_without_edit_form_urls(self):
        page = ConstructedRouteDeepFakePage()
        page.routes["https://www.linkedin.com/in/demo-profile/"] = """
<html>
  <body>
    <main>
      <h1>Demo Profile</h1>
      <p>Security engineer</p>
      <a href="https://www.linkedin.com/in/demo-profile/details/skills/">Skills</a>
      <a href="https://www.linkedin.com/in/demo-profile/details/education/">Education</a>
      <a href="https://www.linkedin.com/in/demo-profile/details/experience/">Experience</a>
      <a href="https://www.linkedin.com/in/demo-profile/details/projects/">Projects</a>
      <a href="https://www.linkedin.com/in/demo-profile/details/certifications/">Licenses &amp; certifications</a>
    </main>
  </body>
</html>
"""
        context = FakeContext(page)
        app_home = tempfile.mkdtemp()
        write_session_state(app_home, "personal")

        def fake_request_with_session(*, url: str, method: str = "GET", payload=None, **_kwargs):
            if method == "GET":
                if url.endswith("/details/skills/"):
                    return 200, url, SKILLS_COMO_HTML
                if url.endswith("/details/education/"):
                    return 200, url, EDUCATION_COMO_HTML
                if url.endswith("/details/experience/"):
                    return 200, url, EXPERIENCE_COMO_HTML
                if url.endswith("/details/projects/"):
                    return 200, url, PROJECTS_COMO_HTML
                if url.endswith("/details/certifications/"):
                    return 200, url, CERTIFICATIONS_COMO_HTML
                raise AssertionError(url)
            pager_id = payload["paginationRequest"]["pagerId"]
            start = payload["paginationRequest"]["requestedArguments"]["payload"]["start"]
            self.assertEqual(start, 0)
            if pager_id == "com.linkedin.sdui.pagers.profile.details.skills":
                return 200, url, make_skills_rsc_response_text(["Skill 1", "Skill 2"])
            if pager_id == "com.linkedin.sdui.pagers.profile.details.education":
                return 200, url, make_accessible_education_rsc_response_text(
                    [
                        {
                            "school": "Example Technical University",
                            "school_url": "https://www.linkedin.com/school/1060201/",
                            "degree": "Bachelor's degree",
                            "field_of_study": "Electrical, Electronics and Communications Engineering",
                            "date_range": "2006 – 2010",
                        }
                    ]
                )
            if pager_id == "com.linkedin.sdui.pagers.profile.details.experience":
                return 200, url, make_accessible_experience_rsc_response_text(
                    [
                        {
                            "title": "Detection Engineer",
                            "company": "ExampleCo",
                            "company_url": "https://www.linkedin.com/company/1809/",
                            "employment_type": "Full-time",
                            "date_range": "Oct 2022 - Present",
                            "duration": "3 yrs 7 mos",
                            "location": "Berlin, Germany · Hybrid",
                            "description": "",
                        }
                    ]
                )
            if pager_id == "com.linkedin.sdui.pagers.profile.details.projects":
                return 200, url, make_accessible_projects_rsc_response_text(
                    [
                        {
                            "name": "Regional Network Modernization Project",
                            "date_range": "Feb 2017 – May 2017",
                            "associated_with": "Example Systems",
                            "description": "",
                        }
                    ]
                )
            if pager_id == "com.linkedin.sdui.pagers.profile.details.certifications":
                return 200, url, make_accessible_licenses_rsc_response_text(
                    [
                        {
                            "name": "Oracle Cloud Infrastructure 2025 Certified Foundations Associate",
                            "issuer": "Oracle",
                            "issue_date_text": "Oct 2025",
                            "expiration_date_text": "",
                            "credential_id": "323136008OCI25FNDCFA",
                            "credential_url": "https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fcatalog-education.oracle.com%2Fbadge",
                            "description": "",
                        }
                    ]
                )
            raise AssertionError(pager_id)

        with patch.object(linkedin_cv, "_request_with_session", side_effect=fake_request_with_session):
            result = linkedin_cv.capture_accessible_profile(
                profile_name="personal",
                url="https://www.linkedin.com/in/demo-profile/",
                confirm_accessible_profile_capture=True,
                app_home=app_home,
                playwright_factory=lambda: FakePlaywrightManager(context),
            )

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["result"]["education"],
            [
                {
                    "school": "Example Technical University",
                    "school_url": "https://www.linkedin.com/school/1060201/",
                    "degree": "Bachelor's degree",
                    "field_of_study": "Electrical, Electronics and Communications Engineering",
                    "date_range": "2006 – 2010",
                    "start_date_text": "2006",
                    "end_date_text": "2010",
                    "grade": "",
                    "activities": "",
                    "description": "",
                    "raw_lines": [],
                }
            ],
        )
        self.assertEqual(
            result["result"]["experience"],
            [
                {
                    "title": "Detection Engineer",
                    "company": "ExampleCo",
                    "company_url": "https://www.linkedin.com/company/1809/",
                    "employment_type": "Full-time",
                    "date_range": "Oct 2022 - Present",
                    "start_date_text": "Oct 2022",
                    "end_date_text": "Present",
                    "is_current": True,
                    "duration": "3 yrs 7 mos",
                    "location": "Berlin, Germany",
                    "description": "",
                    "raw_lines": [],
                }
            ],
        )
        self.assertEqual(
            result["result"]["projects"],
            [
                {
                    "name": "Regional Network Modernization Project",
                    "date_range": "Feb 2017 – May 2017",
                    "start_date_text": "Feb 2017",
                    "end_date_text": "May 2017",
                    "is_current": False,
                    "associated_with": "Example Systems",
                    "project_url": "",
                    "description": "",
                    "raw_lines": [],
                }
            ],
        )
        self.assertEqual(
            result["result"]["licenses_certifications"],
            [
                {
                    "name": "Oracle Cloud Infrastructure 2025 Certified Foundations Associate",
                    "issuer": "Oracle",
                    "issue_date_text": "Oct 2025",
                    "expiration_date_text": "",
                    "credential_id": "323136008OCI25FNDCFA",
                    "credential_url": "https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fcatalog-education.oracle.com%2Fbadge",
                    "description": "",
                    "raw_lines": [],
                }
            ],
        )

    def test_session_login_auto_detects_feed_redirect_and_closes_context(self):
        page = FeedLoginPage()
        context = FakeContext(page)

        result = linkedin_cv.session_login(
            profile_name="personal",
            app_home=tempfile.mkdtemp(),
            timeout_sec=1,
            playwright_factory=lambda: FakePlaywrightManager(context),
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["detected_marker"], "url:/feed/")
        self.assertTrue(context.cookies_written)
        self.assertTrue(context.closed)

    def test_compare_profiles_reports_improvement_areas_without_copying(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            own_path = Path(temp_dir) / "own.json"
            target_path = Path(temp_dir) / "target.json"
            own_path.write_text(
                json.dumps(
                    {
                        "name": "Alex Candidate",
                        "headline": "Security engineer",
                        "about": "",
                        "experience": ["Engineer at OwnCo"],
                        "skills": ["Python"],
                    }
                ),
                encoding="utf-8",
            )
            target_path.write_text(
                json.dumps(
                    {
                        "name": "Jane Candidate",
                        "headline": "Senior Detection Engineer helping SaaS teams reduce alert fatigue",
                        "about": "Builds threat detection programs with measurable incident outcomes.",
                        "experience": ["Lead Security Engineer at ExampleCo"],
                        "skills": ["Detection Engineering", "Python", "SIEM"],
                    }
                ),
                encoding="utf-8",
            )

            result = linkedin_cv.compare_snapshots(own_snapshot=str(own_path), target_snapshot=str(target_path))

        self.assertTrue(result["ok"])
        self.assertIn("about", result["result"]["missing_or_thin_sections"])
        self.assertIn("Do not copy", result["result"]["copying_warning"])

    def test_package_data_and_family_tree_exclude_local_runtime_state(self):
        family_root = REPO_ROOT / "families" / "linkedin-cv"
        pyproject = tomllib.loads((family_root / "pyproject.toml").read_text(encoding="utf-8"))

        package_data = pyproject.get("tool", {}).get("setuptools", {}).get("package-data", {})
        self.assertNotIn("**/*", json.dumps(package_data))

        ignored_generated_parts = {"__pycache__"}
        forbidden_parts = {"profiles", "sessions", "snapshots", "browser-profiles", ".venv"}
        forbidden_names = {"Cookies", "Local State"}
        forbidden_suffixes = {".db", ".sqlite", ".sqlite3", ".ldb", ".log", ".pyc", ".pyo"}
        offenders = []
        for path in family_root.rglob("*"):
            relative = path.relative_to(family_root)
            if any(part in ignored_generated_parts for part in relative.parts):
                continue
            if any(part in forbidden_parts for part in relative.parts):
                offenders.append(str(relative))
            if path.name in forbidden_names:
                offenders.append(str(relative))
            if path.is_file() and path.suffix.lower() in forbidden_suffixes:
                offenders.append(str(relative))

        self.assertEqual(offenders, [])

    def test_codex_and_claude_docs_explain_explicit_accessible_capture_safety(self):
        codex_skill = (
            REPO_ROOT
            / "families"
            / "linkedin-cv"
            / "codex"
            / "skills"
            / "linkedin-cv"
            / "SKILL.md"
        ).read_text(encoding="utf-8")
        claude_skill = (
            REPO_ROOT
            / "families"
            / "linkedin-cv"
            / "claude"
            / "marketplaces"
            / "agent-toolbelt-local"
            / "plugins"
            / "linkedin-cv"
            / "skills"
            / "linkedin-cv"
            / "SKILL.md"
        ).read_text(encoding="utf-8")

        for skill_text in (codex_skill, claude_skill):
            self.assertIn("capture-own", skill_text)
            self.assertIn("--confirm-accessible-profile-capture", skill_text)
            self.assertIn("one explicit profile", skill_text)
            self.assertIn("no search traversal", skill_text.lower())
            self.assertIn("Do not copy", skill_text)


if __name__ == "__main__":
    unittest.main()
