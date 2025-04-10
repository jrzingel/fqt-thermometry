# -*- coding: utf-8 -*-
"""
Created on Wed Apr 09 21:04 2025

@author: james
"""

import urllib3
import json


MSTEAMS_HOOKURL = "https://prod-07.australiasoutheast.logic.azure.com:443/workflows/b5d694e856d64fc69cd9ae8e73e8eec2/triggers/manual/paths/invoke?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=9-Hit9weCVmOG6T0HQuGn1_412lr1ZT8uOrcqX5bvyc"


class TeamsWebhookException(Exception):
    """custom exception for failed webhook call"""
    pass


class ConnectorCard:
    def __init__(self, hookurl, http_timeout=60):
        self.http = urllib3.PoolManager()
        self.payload = {}
        self.hookurl = hookurl
        self.http_timeout = http_timeout

    def text(self, mtext):
        self.payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.5",
                        "body": [
                            {
                                "type": "Container",
                                "horizontalAlignment": "stretch",
                                "items": [
                                    {  # Title
                                        "type": "TextBlock",
                                        "size": "medium",
                                        "weight": "bolder",
                                        "text": "ALARM - Mixing Chamber > 1K",
                                        "style": "heading",
                                        "wrap": True,
                                    },
                                    {  # Fridge identifier
                                        "type": "ColumnSet",
                                        "columns": [
                                            {
                                                "type": "Column",
                                                "items": [
                                                    {
                                                        "type": "Image",
                                                        "style": "person",
                                                        "url": "https://pbs.twimg.com/profile_images/3647943215/d7f12830b3c17a5a9e4afcc370e3a37e_400x400.jpeg",
                                                        "altText": "<fridge name>",
                                                        "size": "small"
                                                    }
                                                ],
                                                "width": "auto"
                                            },
                                            {
                                                "type": "Column",
                                                "items": [
                                                    {
                                                        "type": "TextBlock",
                                                        "weight": "bolder",
                                                        "text": "FRIDGE NAME",
                                                        "wrap": True
                                                    },
                                                    {
                                                        "type": "TextBlock",
                                                        "spacing": "none",
                                                        "text": "Alarm at 17:33 9 April 2025",
                                                        "isSubtle": True,
                                                        "wrap": True,
                                                    }
                                                ],
                                                "width": "stretch"
                                            }
                                        ]
                                    },
                                    {  # Description of the alarm
                                        "type": "TextBlock",
                                        "text": "Mixing chamber has risen over 1K in the past 60 seconds. Comment 'OK' to silence this alarm.",
                                        "wrap": True,
                                    },
                                    {  # List of relevant information
                                        "type": "FactSet",
                                        "facts": [
                                            {
                                                "title": "Sensor T1",
                                                "value": "1.03 K"
                                            },
                                            {
                                                "title": "Sensor T2",
                                                "value": "50.03 K"
                                            }
                                        ]
                                    }
                                ]
                            }
                        ],
                        "actions": [
                            {
                                "type": "Action.OpenUrl",
                                "title": "View",
                                "url": "http://status.fqt.unsw.edu.au/dashboard",
                                "role": "button",
                            }
                        ]
                    }
                }
            ]
        }
        return self

    def send(self):
        headers = {"Content-Type":"application/json"}
        r = self.http.request(
                'POST',
                f'{self.hookurl}',
                body=json.dumps(self.payload).encode('utf-8'),
                headers=headers, timeout=self.http_timeout)
        if r.status < 300:
            return True
        else:
            raise TeamsWebhookException(r.reason)


if __name__ == "__main__":
    myTeamsMessage = ConnectorCard(MSTEAMS_HOOKURL)
    myTeamsMessage.text("this is my test message to the teams channel.")
    myTeamsMessage.send()
