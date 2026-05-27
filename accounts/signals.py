from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.urls import reverse


User = get_user_model()


@receiver(post_save, sender=User)
def send_set_password_link(sender, instance, created, **kwargs):
    if not created:
        return

    if not instance.email:
        return

    uid = urlsafe_base64_encode(force_bytes(instance.pk))
    token = default_token_generator.make_token(instance)

    reset_path = reverse(
        "password_reset_confirm",
        kwargs={"uidb64": uid, "token": token}
    )

    link = f"http://127.0.0.1:8000{reset_path}"

    print("\n=== NEW USER SET PASSWORD LINK ===")
    print(f"User: {instance.username}")
    print(f"Email: {instance.email}")
    print(link)
    print("=================================\n")