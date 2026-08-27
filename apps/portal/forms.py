from django import forms

from apps.geo.models import Habitation
from apps.relief.models import ReliefRequest
from domain.vocab import NEED_LABELS, NeedType


class PublicReportForm(forms.ModelForm):
    habitation_code = forms.CharField(
        label="Habitation code",
        max_length=12,
        help_text="Printed on the panchayat notice board, e.g. DBG012",
    )
    needs = forms.MultipleChoiceField(
        label="What is needed",
        choices=[(n.value, NEED_LABELS[n]) for n in NeedType],
        widget=forms.CheckboxSelectMultiple,
    )
    water_depth_cm = forms.IntegerField(
        label="Water depth in centimetres", required=False, min_value=0, max_value=800,
        help_text="Leave blank if there is no standing water",
    )
    reporter_phone = forms.CharField(label="Phone number", max_length=20)
    reporter_language = forms.ChoiceField(
        label="Reply in",
        choices=[("en", "English"), ("hi", "Hindi"), ("bn", "Bengali")],
        initial="en",
    )

    class Meta:
        model = ReliefRequest
        fields = [
            "total_members", "infants_under_2", "children_2_to_12",
            "pregnant_or_lactating", "elderly_over_60", "persons_with_disability",
            "chronically_ill", "livestock_count", "has_pucca_house",
            "single_woman_headed", "road_status", "is_cut_off", "people_trapped",
        ]
        labels = {
            "total_members": "People in the household",
            "infants_under_2": "Infants under 2",
            "children_2_to_12": "Children 2 to 12",
            "pregnant_or_lactating": "Pregnant or lactating women",
            "elderly_over_60": "Members over 60",
            "persons_with_disability": "Persons with disability",
            "chronically_ill": "Members on regular medication",
            "livestock_count": "Livestock",
            "has_pucca_house": "The house is pucca (concrete)",
            "single_woman_headed": "Household headed by a woman alone",
            "road_status": "Road to the habitation",
            "is_cut_off": "The habitation is cut off",
            "people_trapped": "People trapped right now",
        }

    def clean_habitation_code(self):
        code = self.cleaned_data["habitation_code"].strip().upper()
        if not Habitation.objects.filter(code=code).exists():
            raise forms.ValidationError(
                f"No habitation registered under {code}. Check the notice board code."
            )
        return code

    def habitation(self) -> Habitation:
        return Habitation.objects.get(code=self.cleaned_data["habitation_code"])

    def to_intake_kwargs(self) -> dict:
        """Everything ReliefService.intake() needs, and nothing it does not.

        The form knows which of its fields are model fields; the view should
        not have to introspect _meta to find out.
        """
        data = self.cleaned_data
        fields = {name: data[name] for name in self.Meta.fields}
        fields["water_depth_m"] = round((data.get("water_depth_cm") or 0) / 100, 2)
        return fields


class OverrideForm(forms.Form):
    priority = forms.ChoiceField(
        choices=[(p, p) for p in ("RED", "ORANGE", "YELLOW", "GREEN")]
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Recorded against your name in the audit trail.",
    )


class MoveForm(forms.Form):
    to_state = forms.CharField(max_length=16)
    note = forms.CharField(required=False, max_length=240)
    proof_reference = forms.CharField(required=False, max_length=64)
