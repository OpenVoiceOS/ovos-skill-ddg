#!/usr/bin/env python3
from setuptools import setup

# skill_id=package_name:SkillClass
PLUGIN_ENTRY_POINT = 'mycroft-fallback-duck-duck-go.mycroftai=skill_ddg:DuckDuckGoSkill'
# in this case the skill_id is defined to purposefully replace the mycroft version of the skill,
# or rather to be replaced by it in case it is present. all skill directories take precedence over plugin skills

setup(
    # this is the package name that goes on pip
    name='skill-ddg',
    version='0.0.1',
    description='mycroft/ovos duck duck go skill plugin',
    url='https://github.com/JarbasSkills/skill-ddg',
    author='JarbasAi',
    author_email='jarbasai@mailfence.com',
    license='Apache-2.0',
    package_dir={"skill_ddg": ""},
    package_data={'skill_ddg': ['locale/*', 'vocab/*', "dialog/*"]},
    packages=['skill_ddg'],
    include_package_data=True,
    install_requires=["ovos-plugin-manager>=0.0.1a3",
                      "simplematch",
                      "neon-lang-plugin-libretranslate",
                      "quebra_frases"],
    keywords='ovos skill plugin',
    entry_points={'ovos.plugin.skill': PLUGIN_ENTRY_POINT}
)
