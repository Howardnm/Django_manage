import logging
import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

class FeedbackService:
    """
    行为回传服务：将子系统（电子手册）中的会员行为实时同步回主系统审计。
    """
    
    @staticmethod
    def push_activity(member_token, action, target_name):
        """
        发送行为日志到主系统 API。
        action: VIEW, DOWNLOAD_TDS, etc.
        """
        if not member_token:
            return False

        payload = {
            'logs': [
                {
                    'member_token': member_token,
                    'action': action,
                    'target_name': target_name,
                    'timestamp': timezone.now().isoformat()
                }
            ]
        }
        
        try:
            # 这里的 URL 和 Token 均从 settings 中获取，确保环境适配
            url = f"{settings.REMOTE_API_BASE_URL}auth/feedback/"
            headers = {
                'X-Internal-Api-Token': settings.INTERNAL_API_TOKEN,
                'Content-Type': 'application/json'
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=5)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Feedback Service push failed for token {member_token}: {e}")
            return False
