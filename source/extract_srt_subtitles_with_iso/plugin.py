#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    Written by:               Josh.5 <jsunnex@gmail.com>, EdBaynes
    Date:                     11 May 2023, (16:41 AM)
 
    Copyright:
        Copyright (C) 2021 Josh Sunnex

        This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
        Public License as published by the Free Software Foundation, version 3.

        This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the
        implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
        for more details.

        You should have received a copy of the GNU General Public License along with this program.
        If not, see <https://www.gnu.org/licenses/>.

"""
import logging
import os
import re
import babelfish

from unmanic.libs.unplugins.settings import PluginSettings

from extract_srt_subtitles_with_iso.lib.ffmpeg import StreamMapper, Probe, Parser

# Configure plugin logger
logger = logging.getLogger("Unmanic.Plugin.extract_srt_subtitles_with_iso")

subtitles_to_remove = []

class Settings(PluginSettings):
    settings = {
        "language_code":        '1',
        "use_sdh_extension":    '',
        "use_forced_extension": '',
        "default_language":     'en',
        "use_title_failback":   True,
        "use_regional":         True,
        "latin_spanish":        '1',
    }

    def __init__(self, *args, **kwargs):
        super(Settings, self).__init__(*args, **kwargs)
        self.form_settings = {
            "language_code": {
                "input_type":     "select",
                "select_options": [
                    {
                        "value": '1',
                        "label": "Use ISO-639-1 2-letter format.        (example: en,  fr,  pt,  de,  nl,  zh,  el)",
                    },
                    {
                        "value": '2',
                        "label": "Use ISO-639-2/B 3-letter format.      (example: eng, fre, por, ger, dut, chi, gre)",
                    },
                    {
                        "value": '3',
                        "label": "Use ISO-639-2/T 3-letter format.      (example: eng, fra, por, deu, nld, zho, ell)",
                    },
                    {
                        "value": '4',
                        "label": "Use OpenSubtitles 3-letter format.    (example: eng, fre, por, ger, dut, chi, ell)",
                    },
                ],
                "label":          "Language Code extension format",
            },
            "use_sdh_extension": {
                "input_type":     "select",
                "select_options": [
                    {
                        "value": '',
                        "label": "Don't use",
                    },
                    {
                        "value": 'sdh',
                        "label": "Subtitles for the Deaf and Hard of Hearing (SDH):     '.sdh' sufix will be added.",
                    },
                    {
                        "value": 'cc',
                        "label": "Closed Captioning (CC):                               '.cc' sufix will be added.",
                    },
                    {
                        "value": 'hi',
                        "label": "Hearing-Impaired (HI):                                '.hi' sufix will be added. *WARNING: This might conflict with Hindi Language",
                    },
                ],
                "label":          "Hearing-impaired subtitles extension. (To be added after Language Code)",
            },
            "use_forced_extension": {
                "input_type":     "select",
                "select_options": [
                    {
                        "value": '',
                        "label": "Don't use",
                    },
                    {
                        "value": 'forced',
                        "label": "'.forced' sufix will be added after language code",
                    },
                ],
                "label":          "Forced subtitles extension. (To be added after Language Code)",
            },
            "default_language": {
                "label":          "Specify a sufix for subtitle tracks with no language or unknown language to be tagged with. Leave empty to disable.",
            },
            "use_title_failback": {
                "label":          "Use Subtitle description if no language information exists",
            },
            "use_regional": {
                "label":          "Try defining Region Subtag from Subtitle description. (For exemple: 'pt-BR' for Brazilian Portuguese or 'fr-CA' for Canadian French)",
            },
            "latin_spanish": {
                "input_type":     "select",
                "select_options": [
                    {
                        "value": '1',
                        "label": "Use '.ea' extension For Latin American Spanish",
                    },
                    {
                        "value": '2',
                        "label": "Use '.es-419' extension For Latin American Spanish",
                    },
                ],
                "label":          "Latin American Spanish prefered extension (Region Subtag must be selected)",
            }
        }

class PluginStreamMapper(StreamMapper):
    def __init__(self):
        super(PluginStreamMapper, self).__init__(logger, ['subtitle'])
        self.sub_streams = []
        self.settings = None

    def set_settings(self, settings):
        self.settings = settings

    def test_stream_needs_processing(self, stream_info: dict):
        """Any text based will need to be processed"""
        if stream_info.get('codec_name').lower() in ['srt', 'subrip', 'mov_text']:
            return True
        return False

    def custom_stream_mapping(self, stream_info: dict, stream_id: int):
        # Find a tag for this subtitle
        subtitle_tag = ''
        stream_tags = stream_info.get('tags', {})

        language_tag = ''
        sdh_tag      = ''
        forced_tag   = ''
        stream_lang  = ''
        stream_title = ''

#       Get Plugin Settings
        language_code           = self.settings.get_setting('language_code')
        use_sdh_extension       = self.settings.get_setting('use_sdh_extension')
        use_forced_extension    = self.settings.get_setting('use_forced_extension')
        default_language        = self.settings.get_setting('default_language')
        use_title_failback      = self.settings.get_setting('use_title_failback')
        use_regional            = self.settings.get_setting('use_regional')
        latin_spanish           = self.settings.get_setting('latin_spanish')

        if stream_tags.get('language'):
            stream_lang = stream_tags.get('language').lower()
        if stream_tags.get('title'):
            stream_title =  stream_tags.get('title').lower()
        
#       If language is 'und' or blank use default language IF set
        if stream_lang == 'und' or stream_lang == '':
            stream_lang = default_language

        if len(stream_lang) == 2:
            try:
                language = babelfish.Language.fromalpha2(stream_lang)
            except:
                language = ''
        elif len(stream_lang) == 3:  
            try:
                language = babelfish.Language.fromalpha3b(stream_lang)
            except:
                try:
                    language = babelfish.Language.fromalpha3t(stream_lang)
                except:
                    try:
                        language = babelfish.Language.fromopensubtitles(stream_lang)
                    except:
                        language = ''
        else:
            language = ''

        if language:
            # Use ISO-639-1 2-letter format.        (example: en,  fr,  pt,  de,  nl,  zh,  el)
            if language_code == '1':
                language_tag = language.alpha2

            # Use ISO-639-2/B 3-letter format.      (example: eng, fre, por, ger, dut, chi, gre)
            elif language_code == '2':
                language_tag = language.alpha3b

            # Use ISO-639-2/T 3-letter format.      (example: eng, fra, por, deu, nld, zho, ell)
            elif language_code == '3':
                language_tag = language.alpha3

            # Use OpenSubtitles 3-letter format.    (example: eng, fre, por, ger, dut, chi, ell)
            elif language_code == '4':
                language_tag = language.opensubtitles

            if use_regional:
                if language == 'en':                                        # ENGLISH
                    if ( 'united' in stream_title and 'states' in stream_title ) or 'usa' in stream_title or 'america' in stream_title:
                        region_tag = 'US'
                    elif ( 'united' in stream_title and 'kingdom' in stream_title ) or ( 'great' in stream_title and 'britain' in stream_title ) or 'uk' in stream_title:
                        region_tag = 'GB'
                    elif 'australia' in stream_title:
                        region_tag = 'AU'
                    elif 'canad' in stream_title:
                        region_tag = 'CA'
                    elif 'zealand' in stream_title:
                        region_tag = 'NZ'
                    
                elif language == 'fr':                                      # FRENCH
                    if 'canad' in stream_title or 'quebec' in stream_title or 'québéc' in stream_title:
                        region_tag = 'CA'
                    elif 'belgi' in stream_title:
                        region_tag = 'BE'

                elif language == 'pt':                                      # PORTUGUESE
                    if 'brazil' in stream_title or 'brasil' in stream_title:
                        region_tag = 'BR'

                elif language == 'es':                                      # SPANISH
                    if 'mexic' in stream_title or 'méxic' in stream_title:
                        region_tag = 'MX'
                    if 'latin' in stream_title or 'america' in stream_title:
                        if latin_spanish == '1':     # Use '.ea' extension For Latin American Spanish
                            language_tag = 'ea'
                        elif latin_spanish == '2':   # Use '.es-419' extension For Latin American Spanish
                            region_tag = '419'
        elif stream_lang:
            language_tag = stream_lang

#       Check if the user selected a SDH extension
        if use_sdh_extension:
            # Check the title for Hearing Impared or SDH or CC information            
            if 'sdh' in stream_title or 'cc' in stream_title or 'hi' in stream_title:
                sdh_tag = use_sdh_extension

#       Check if the user selected a Forced extension
        if use_forced_extension:
            if 'force' in stream_title:
                forced_tag = use_forced_extension                
        
        if language_tag:
            subtitle_tag = "{}.{}".format(subtitle_tag, language_tag)
            if region_tag:
                subtitle_tag = "{}.{}".format(subtitle_tag, region_tag)
            if sdh_tag:
                subtitle_tag = "{}.{}".format(subtitle_tag, sdh_tag)
            if forced_tag:
                subtitle_tag = "{}.{}".format(subtitle_tag, forced_tag)
           
        else:
#           If user choose to use Stream Description for tracks without a language
            if use_title_failback and stream_title:
                subtitle_tag = "{}.{}".format(subtitle_tag, stream_tags.get('title'))

        # If there were no tags, just number the file
        if not subtitle_tag:
            subtitle_tag = "{}.{}".format(subtitle_tag, stream_info.get('index'))

        # Ensure subtitle tag does not contain whitespace
        subtitle_tag = re.sub('\s', '-', subtitle_tag)

        self.sub_streams.append(
            {
                'stream_id':      stream_id,
                'subtitle_tag':   subtitle_tag,
                'stream_mapping': ['-map', '0:s:{}'.format(stream_id)],
            }
        )

        # Copy the streams to the destination. This will actually do nothing...
        return {
            'stream_mapping':  ['-map', '0:s:{}'.format(stream_id)],
            'stream_encoding': ['-c:s:{}'.format(stream_id), 'copy'],
        }

    def get_ffmpeg_args(self):
        """
        Overwrite default function. We only need the first lot of args.

        :return:
        """
        args = []

        # Add generic options first
        args += self.generic_options

        # Add the input file
        # This class requires at least one input file specified with the input_file attribute
        if not self.input_file:
            raise Exception("Input file has not been set")
        args += ['-i', self.input_file]

        # Add other main options
        args += self.main_options

        # Add advanced options. This includes the stream mapping and the encoding args
        args += self.advanced_options

        return args


def on_library_management_file_test(data):
    """
    Runner function - enables additional actions during the library management file tests.

    The 'data' object argument includes:
        library_id                      - The library that the current task is associated with
        path                            - String containing the full path to the file being tested.
        issues                          - List of currently found issues for not processing the file.
        add_file_to_pending_tasks       - Boolean, is the file currently marked to be added to the queue for processing.
        priority_score                  - Integer, an additional score that can be added to set the position of the new task in the task queue.
        shared_info                     - Dictionary, information provided by previous plugin runners. This can be appended to for subsequent runners.

    :param data:
    :return:

    """
    # Configure settings object (maintain compatibility with v1 plugins)
    if data.get('library_id'):
        settings = Settings(library_id=data.get('library_id'))
    else:
        settings = Settings()

    # Get the path to the file
    abspath = data.get('path')

    # Get file probe
    probe = Probe(logger, allowed_mimetypes=['video'])
    if 'ffprobe' in data.get('shared_info', {}):
        if not probe.set_probe(data.get('shared_info', {}).get('ffprobe')):
            # Failed to set ffprobe from shared info.
            # Probably due to it being for an incompatible mimetype declared above
            return
    elif not probe.file(abspath):
        # File probe failed, skip the rest of this test
        return
    # Set file probe to shared infor for subsequent file test runners
    if 'shared_info' in data:
        data['shared_info'] = {}
    data['shared_info']['ffprobe'] = probe.get_probe()

    # Get stream mapper
    mapper = PluginStreamMapper()
    mapper.set_settings(settings)
    mapper.set_probe(probe)

    if mapper.streams_need_processing():
        # Mark this file to be added to the pending tasks
        data['add_file_to_pending_tasks'] = True
        logger.debug("File '{}' should be added to task list. Probe found streams require processing.".format(abspath))
    else:
        logger.debug("File '{}' does not contain streams require processing.".format(abspath))


def on_worker_process(data):
    """
    Runner function - enables additional configured processing jobs during the worker stages of a task.

    The 'data' object argument includes:
        exec_command            - A command that Unmanic should execute. Can be empty.
        command_progress_parser - A function that Unmanic can use to parse the STDOUT of the command to collect progress stats. Can be empty.
        file_in                 - The source file to be processed by the command.
        file_out                - The destination that the command should output (may be the same as the file_in if necessary).
        original_file_path      - The absolute path to the original file.
        repeat                  - Boolean, should this runner be executed again once completed with the same variables.

    DEPRECIATED 'data' object args passed for legacy Unmanic versions:
        exec_ffmpeg             - Boolean, should Unmanic run FFMPEG with the data returned from this plugin.
        ffmpeg_args             - A list of Unmanic's default FFMPEG args.

    :param data:
    :return:

    """
    # Default to no FFMPEG command required. This prevents the FFMPEG command from running if it is not required
    data['exec_command'] = []
    data['repeat'] = False

    # Get the path to the file
    abspath = data.get('file_in')

    # Get file probe
    probe = Probe(logger, allowed_mimetypes=['video'])
    if not probe.file(abspath):
        # File probe failed, skip the rest of this test
        return

    # Configure settings object (maintain compatibility with v1 plugins)
    if data.get('library_id'):
        settings = Settings(library_id=data.get('library_id'))
    else:
        settings = Settings()

    # Get stream mapper
    mapper = PluginStreamMapper()
    mapper.set_settings(settings)
    mapper.set_probe(probe)

    split_original_file_path = os.path.splitext(data.get('original_file_path'))
    original_file_directory = os.path.dirname(data.get('original_file_path'))

    if mapper.streams_need_processing():
        # Set the input file
        mapper.set_input_file(abspath)

        # Get generated ffmpeg args
        ffmpeg_args = mapper.get_ffmpeg_args()

        # Append STR extract args
        for sub_stream in mapper.sub_streams:
            stream_mapping = sub_stream.get('stream_mapping', [])
            subtitle_tag = sub_stream.get('subtitle_tag')

            ffmpeg_args += stream_mapping
            ffmpeg_args += [
                "-y",
                os.path.join(original_file_directory, "{}{}.srt".format(split_original_file_path[0], subtitle_tag)),
            ]

        # Apply ffmpeg args to command
        data['exec_command'] = ['ffmpeg']
        data['exec_command'] += ffmpeg_args

        # Set the parser
        parser = Parser(logger)
        parser.set_probe(probe)
        data['command_progress_parser'] = parser.parse_progress