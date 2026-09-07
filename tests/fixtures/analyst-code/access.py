def may_download(is_member, suspended):
    return is_member or not suspended
