from django import forms

from .models import SpecificationTemplate


class SpecificationTemplateForm(forms.ModelForm):
    cover_page = forms.CharField(widget=forms.Textarea(attrs={"rows":4}), required=False)
    document_title = forms.CharField(required=False)
    introduction = forms.CharField(widget=forms.Textarea(attrs={"rows":4}), required=False)
    header = forms.CharField(widget=forms.Textarea(attrs={"rows":3}), required=False)
    footer = forms.CharField(widget=forms.Textarea(attrs={"rows":3}), required=False)
    closing_statement = forms.CharField(widget=forms.Textarea(attrs={"rows":3}), required=False)
    company_info = forms.CharField(widget=forms.Textarea(attrs={"rows":3}), required=False)
    logo_options = forms.CharField(widget=forms.Textarea(attrs={"rows":2}), required=False)
    typography = forms.CharField(widget=forms.Textarea(attrs={"rows":2}), required=False)
    colours = forms.CharField(widget=forms.Textarea(attrs={"rows":2}), required=False)
    spacing = forms.CharField(widget=forms.Textarea(attrs={"rows":2}), required=False)

    class Meta:
        model = SpecificationTemplate
        fields = ["name", "key", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cfg = getattr(self.instance, "config", {}) or {}
        # populate initial values from the JSON config
        self.fields["cover_page"].initial = cfg.get("cover_page", "")
        self.fields["document_title"].initial = cfg.get("document_title", "")
        self.fields["introduction"].initial = cfg.get("introduction", "")
        self.fields["header"].initial = cfg.get("header", "")
        self.fields["footer"].initial = cfg.get("footer", "")
        self.fields["closing_statement"].initial = cfg.get("closing_statement", "")
        self.fields["company_info"].initial = cfg.get("company_info", "")
        self.fields["logo_options"].initial = cfg.get("logo_options", "")
        self.fields["typography"].initial = cfg.get("typography", "")
        self.fields["colours"].initial = cfg.get("colours", "")
        self.fields["spacing"].initial = cfg.get("spacing", "")

    def save(self, commit=True):
        inst = super().save(commit=False)
        inst.config = {
            "cover_page": self.cleaned_data.get("cover_page", ""),
            "document_title": self.cleaned_data.get("document_title", ""),
            "introduction": self.cleaned_data.get("introduction", ""),
            "header": self.cleaned_data.get("header", ""),
            "footer": self.cleaned_data.get("footer", ""),
            "closing_statement": self.cleaned_data.get("closing_statement", ""),
            "company_info": self.cleaned_data.get("company_info", ""),
            "logo_options": self.cleaned_data.get("logo_options", ""),
            "typography": self.cleaned_data.get("typography", ""),
            "colours": self.cleaned_data.get("colours", ""),
            "spacing": self.cleaned_data.get("spacing", ""),
        }
        if commit:
            inst.save()
        return inst
