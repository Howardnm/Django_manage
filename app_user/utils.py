import random
import string
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
import logging

logger = logging.getLogger(__name__)

# 生成验证码图片
def generate_captcha():
    # 定义图片大小
    width, height = 120, 40
    # 创建图片对象
    image = Image.new('RGB', (width, height), (255, 255, 255))
    # 创建画笔
    draw = ImageDraw.Draw(image)
    # 生成随机字体 (如果没有字体文件，使用默认)
    # font = ImageFont.truetype('arial.ttf', 36) 
    # 为了兼容性，这里尝试加载默认字体，或者简单的绘制
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except:
        font = ImageFont.load_default()

    # 生成随机验证码
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

    # 绘制验证码
    for i, char in enumerate(code):
        # 随机颜色
        color = (random.randint(0, 150), random.randint(0, 150), random.randint(0, 150))
        draw.text((10 + i * 25, 5), char, font=font, fill=color)

    # 添加干扰点
    for _ in range(100):
        draw.point((random.randint(0, width), random.randint(0, height)), fill=(200, 200, 200))

    # 转为字节流
    buf = BytesIO()
    image.save(buf, 'png')
    return buf.getvalue(), code

# 发送邮箱验证码
def send_verification_email(email):
    code = ''.join(random.choices(string.digits, k=6))
    subject = '【项目管理系统】验证码'
    message = f'您的验证码是：{code}，有效期5分钟。请勿将验证码泄露给他人。'
    from_email = settings.DEFAULT_FROM_EMAIL
    
    try:
        send_mail(subject, message, from_email, [email], fail_silently=False)
        logger.info(f"Email sent to {email}: {code}")
        return code, True, None  # 返回 (验证码, 是否成功, 错误信息)
    except Exception as e:
        logger.error(f"Error sending email to {email}: {e}")
        # 在开发环境下，如果发送失败，依然打印验证码方便调试，并视为成功
        if settings.DEBUG:
            print(f"DEBUG: Mock Send Email to {email}: {code}")
            return code, True, None
        
        # 生产环境返回失败信息
        return None, False, str(e)

# 发送注册成功邮件
def send_register_success_email(user, request):
    subject = '【项目管理系统】注册成功通知'
    
    # 构建登录链接 (尝试获取完整的 URL)
    login_url = request.build_absolute_uri(reverse('login'))
    
    message = f"""
尊敬的 {user.username}：

恭喜您成功注册【项目管理系统】账号！

您的账户信息如下：
----------------------------
用户名：{user.username}
注册邮箱：{user.email}
----------------------------

您可以点击下方链接登录系统：
{login_url}

如果链接无法点击，请复制并粘贴到浏览器地址栏中访问。

祝您使用愉快！
项目管理系统团队
    """
    
    from_email = settings.DEFAULT_FROM_EMAIL
    
    try:
        send_mail(subject, message, from_email, [user.email], fail_silently=True)
        logger.info(f"Register success email sent to {user.email}")
    except Exception as e:
        logger.error(f"Error sending register success email to {user.email}: {e}")