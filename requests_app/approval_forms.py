from django import forms

class ApprovalActionForm(forms.Form):
    action = forms.ChoiceField(
        choices=[
            ("APPROVE", "Approve"),
            ("REJECT", "Reject"),
            ("RETURN", "Return for changes"),
        ]
    )
    comment = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}),
        required=False
    )