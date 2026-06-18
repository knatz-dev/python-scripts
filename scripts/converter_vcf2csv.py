import csv
from datetime import datetime
from pathlib import Path
from typing import Any

import vobject
from vobject.base import Component

INPUT_FILE = Path("contacts.vcf")
OUTPUT_FILE = Path(f"{datetime.now().strftime('%Y%m%d%H%M%S')}-contacts.csv")

PHONE_COLUMNS = {
    "MobilePhone": "Mobile Phone",
    "HomePhone": "Home Phone",
    "WorkPhone": "Work Phone",
    "OtherPhone": "Other Phone",
}

EMAIL_COLUMNS = {
    "PersonalEmail": "Personal Email",
    "WorkEmail": "Work Email",
    "OtherEmail": "Other Email",
}

ADDRESS_COLUMNS = {
    "HomeAddress": "Home Address",
    "WorkAddress": "Work Address",
    "OtherAddress": "Other Address",
}

def build_column_map() -> dict[str, str]:
    """Build mapping of internal row keys to human-readable CSV headers."""
    return {
        "FullName": "Full Name",
        "Prefix": "Prefix",
        "FirstName": "First Name",
        "MiddleName": "Middle Name",
        "LastName": "Last Name",
        "Suffix": "Suffix",
        "Nickname": "Nickname",
        "Company": "Company",
        "JobTitle": "Job Title",
        "Birthday": "Birthday",
        **PHONE_COLUMNS,
        **EMAIL_COLUMNS,
        **ADDRESS_COLUMNS,
        "Notes": "Notes",
        "Website": "Website",
    }

class DataCleaner:
    """Utility helpers for normalising raw vCard values."""

    DEFAULT_REPLACEMENT = "N/A"

    @staticmethod
    def clean(value: Any) -> str:
        """
        Convert a raw value into a clean string.

        Handles:
        - None
        - strings
        - lists/tuples
        - date-like objects
        - other objects returned by vobject
        """
        if value is None:
            return ""

        if isinstance(value, (list, tuple)):
            return "; ".join(
                cleaned_value
                for item in value
                if (cleaned_value := DataCleaner.clean(item))
            )

        return str(value).strip()

    @staticmethod
    def remove_nulls(data: list[str]) -> list[str]:
        """Remove empty or falsy values from a list."""
        return [item for item in data if item]

    @classmethod
    def replace_nulls(
        cls,
        data: list[str],
        replacement: str | None = None,
    ) -> list[str]:
        """Replace empty values with a fallback replacement string."""
        actual_replacement = replacement or cls.DEFAULT_REPLACEMENT
        return [item if item else actual_replacement for item in data]

    @staticmethod
    def trim_spaces(data: list[str]) -> list[str]:
        """Trim whitespace from every string in the list."""
        return [item.strip() for item in data]

class Extractor:
    """Helpers for extracting metadata from vCard fields."""

    @staticmethod
    def get_param_values(item: Any, param_name: str) -> set[str]:
        """
        Extract normalized parameter values from a vCard field.

        Handles values such as:
        - TYPE=CELL
        - TYPE=CELL,VOICE
        - TYPE=['CELL', 'VOICE']
        - type=home,internet
        """
        raw_values = item.params.get(param_name.upper(), [])

        if isinstance(raw_values, str):
            raw_values = [raw_values]

        result: set[str] = set()

        for raw_value in raw_values:
            cleaned_value = DataCleaner.clean(raw_value).upper()

            if not cleaned_value:
                continue

            # Some vCards store multiple types inside one comma-separated value.
            for token in cleaned_value.split(","):
                token = token.strip()

                if token:
                    result.add(token)

        return result

class Contact:
    """Utility functions for extracting contact-level vCard data."""

    @staticmethod
    def get_raw_values(contact: Component, field_name: str) -> list[Any]:
        """
        Retrieve raw vCard field entries.

        Args:
            contact: vobject contact component.
            field_name: vCard field name, for example fn, n, tel, email.

        Returns:
            A list of matching vobject field items.
        """
        return contact.contents.get(field_name.lower(), [])

    @staticmethod
    def get_first_value(contact: Component, field_name: str) -> str:
        """
        Get the first value for a given field.

        Suitable for fields where only the first value is useful, such as:
        - FN
        - NICKNAME
        - TITLE
        - BDAY
        - URL
        - NOTE
        """
        values = Contact.get_raw_values(contact, field_name)

        if not values:
            return ""

        return DataCleaner.clean(values[0].value)

    @staticmethod
    def get_display_name(contact: Component) -> str:
        """
        Determine the contact display name.

        FN is preferred.
        If FN is missing, the name is built from structured N fields.
        """
        full_name = Contact.get_first_value(contact, "fn")

        if full_name:
            return full_name

        name = Contact.get_structured_name(contact)

        return " ".join(
            part
            for part in [
                name["Prefix"],
                name["FirstName"],
                name["MiddleName"],
                name["LastName"],
                name["Suffix"],
            ]
            if part
        )

    @staticmethod
    def get_structured_name(contact: Component) -> dict[str, str]:
        """
        Extract structured name components from the vCard N field.

        Returns:
            Prefix, FirstName, MiddleName, LastName, Suffix.
        """
        values = Contact.get_raw_values(contact, "n")

        if not values:
            return {
                "Prefix": "",
                "FirstName": "",
                "MiddleName": "",
                "LastName": "",
                "Suffix": "",
            }

        name = values[0].value

        return {
            "Prefix": DataCleaner.clean(getattr(name, "prefix", "")),
            "FirstName": DataCleaner.clean(getattr(name, "given", "")),
            "MiddleName": DataCleaner.clean(getattr(name, "additional", "")),
            "LastName": DataCleaner.clean(getattr(name, "family", "")),
            "Suffix": DataCleaner.clean(getattr(name, "suffix", "")),
        }

class Address:
    """Utility functions for working with vCard addresses."""

    @staticmethod
    def format(addr: Any) -> str:
        """
        Format a structured vCard address into a single readable string.

        Typical fields:
        - box
        - extended
        - street
        - city
        - region
        - code
        - country
        """
        parts = [
            getattr(addr, "box", ""),
            getattr(addr, "extended", ""),
            getattr(addr, "street", ""),
            getattr(addr, "city", ""),
            getattr(addr, "region", ""),
            getattr(addr, "code", ""),
            getattr(addr, "country", ""),
        ]

        cleaned_parts = [
            cleaned_part
            for part in parts
            if (cleaned_part := DataCleaner.clean(part))
        ]

        return ", ".join(cleaned_parts)

    @staticmethod
    def get_column_key(addr) -> str:
        types = Extractor.get_param_values(addr, "TYPE")

        if "HOME" in types:
            return "HomeAddress"

        if "WORK" in types:
            return "WorkAddress"

        return "OtherAddress"

class Email:
    @staticmethod
    def get_column_key(email) -> str:
        types = Extractor.get_param_values(email, "TYPE")

        if "WORK" in types:
            return "WorkEmail"

        if types & {"HOME", "PERSONAL", "INTERNET"}:
            return "PersonalEmail"

        return "OtherEmail"

class Phone:
    @staticmethod
    def get_column_key(phone) -> str:
        types = Extractor.get_param_values(phone, "TYPE")

        if types & {"CELL", "MOBILE"}:
            return "MobilePhone"

        if "HOME" in types:
            return "HomePhone"

        if "WORK" in types:
            return "WorkPhone"

        return "OtherPhone"

class vContactProcessor:
    """Processes vCard contacts into flat row dictionaries."""

    @staticmethod
    def _append_to_column(row: dict[str, str], column_key: str, value: str) -> None:
        """
        Append a value to a row column.

        Multiple values are joined using semicolon separation.
        """
        if not value:
            return

        existing_value = row.get(column_key, "")

        row[column_key] = (
            value
            if not existing_value
            else f"{existing_value}; {value}"
        )

    @staticmethod
    def _init_columns(row: dict[str, str], columns: dict[str, str]) -> None:
        """Initialize all expected columns with empty strings."""
        for column_key in columns:
            row[column_key] = ""

    def add_phone_fields(self, row: dict[str, str], phones: list[Any]) -> None:
        """Populate phone-related fields in the CSV row."""
        self._init_columns(row, PHONE_COLUMNS)

        for phone in phones:
            value = DataCleaner.clean(phone.value)
            column_key = Phone.get_column_key(phone)
            self._append_to_column(row, column_key, value)

    def add_email_fields(self, row: dict[str, str], emails: list[Any]) -> None:
        """Populate email-related fields in the CSV row."""
        self._init_columns(row, EMAIL_COLUMNS)

        for email in emails:
            value = DataCleaner.clean(email.value)
            column_key = Email.get_column_key(email)
            self._append_to_column(row, column_key, value)

    def add_address_fields(self, row: dict[str, str], addresses: list[Any]) -> None:
        """Populate address-related fields in the CSV row."""
        self._init_columns(row, ADDRESS_COLUMNS)

        for address in addresses:
            value = Address.format(address.value)
            column_key = Address.get_column_key(address)
            self._append_to_column(row, column_key, value)

    def contact_to_row(self, contact: Component) -> dict[str, str]:
        """Convert a vCard contact into a flattened CSV row."""
        row = {
            "FullName": Contact.get_display_name(contact),
            **Contact.get_structured_name(contact),
            "Nickname": Contact.get_first_value(contact, "nickname"),
            "Company": Contact.get_first_value(contact, "org"),
            "JobTitle": Contact.get_first_value(contact, "title"),
            "Birthday": Contact.get_first_value(contact, "bday"),
            "Website": Contact.get_first_value(contact, "url"),
            "Notes": Contact.get_first_value(contact, "note"),
        }

        self.add_phone_fields(row, Contact.get_raw_values(contact, "tel"))
        self.add_email_fields(row, Contact.get_raw_values(contact, "email"))
        self.add_address_fields(row, Contact.get_raw_values(contact, "adr"))

        return row

class ContactsExporter:
    """Exports vCard contacts into CSV format."""

    @staticmethod
    def to_csv(input_path: Path, output_path: Path) -> None:
        """
        Convert a VCF file into a CSV file.

        Args:
            input_path: Path to the source .vcf file.
            output_path: Path to the generated .csv file.
        """
        processor = vContactProcessor()
        column_map = build_column_map()

        with (
            input_path.open("r", encoding="utf-8") as vcf_file,
            output_path.open("w", newline="", encoding="utf-8-sig") as csv_file,
        ):
            writer = csv.DictWriter(
                csv_file,
                fieldnames=list(column_map.keys()),
                extrasaction="ignore",
            )

            writer.writerow(column_map)

            for contact in vobject.readComponents(vcf_file):
                writer.writerow(processor.contact_to_row(contact))

if __name__ == "__main__":
    ContactsExporter.to_csv(INPUT_FILE, OUTPUT_FILE)
    print(f"Exported contacts to {OUTPUT_FILE}")