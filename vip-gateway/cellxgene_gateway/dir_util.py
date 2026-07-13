# Copyright 2019 Novartis Institutes for BioMedical Research Inc. Licensed
# under the Apache License, Version 2.0 (the "License"); you may not use
# this file except in compliance with the License. You may obtain a copy
# of the License at http://www.apache.org/licenses/LICENSE-2.0. Unless
# required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES
# OR CONDITIONS OF ANY KIND, either express or implied. See the License for
# the specific language governing permissions and limitations under the License.

import os
import stat

from cellxgene_gateway import env
from cellxgene_gateway.cellxgene_exception import CellxgeneException

annotations_suffix = "_annotations"
h5ad_suffix = ".h5ad"


def make_h5ad(el):
    return el[: -len(annotations_suffix)] + h5ad_suffix


def make_annotations(el):
    return el[:-5] + annotations_suffix


def ensure_dir_exists(file_path):
    if not os.path.exists(file_path):
        os.makedirs(file_path, mode=0o777, exist_ok=True)
    else:
        # Ensure existing dirs are group-writable (uid 1999 may need to write)
        try:
            current = stat.S_IMODE(os.stat(file_path).st_mode)
            if not current & stat.S_IWGRP:
                os.chmod(file_path, current | stat.S_IWGRP | stat.S_IXGRP)
        except (OSError, PermissionError):
            pass


def vipconfig_path(h5ad_path):
    """Return the sidecar .vipconfig.json path for a given h5ad file."""
    return os.path.splitext(h5ad_path)[0] + ".vipconfig.json"
