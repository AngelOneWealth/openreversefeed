from django import forms


class UploadForm(forms.Form):
    file = forms.FileField(label="Feed file (CSV, XLS, XLSX, or DBF)")
    registrar = forms.ChoiceField(
        choices=[("cams", "CAMS"), ("kfintech", "KFintech")],
        widget=forms.RadioSelect,
    )
    uploaded_by = forms.CharField(max_length=100, initial="operator")
