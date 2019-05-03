import numpy as np

try:
    from scipy.sparse.linalg import spsolve
    from scipy.sparse import coo_matrix, eye
except ImportError:
    pass


def filter_laplacian(mesh,
                     lamb=0.5,
                     iterations=10,
                     implicit_time_integration=False,
                     volume_constraint=True,
                     laplacian_operator=None):
    """
    Smooth a mesh in-place using laplacian smoothing.
    Articles
    1 - "Improved Laplacian Smoothing of Noisy Surface Meshes"
       J. Vollmer, R. Mencl, and H. Muller
    2 - "Implicit Fairing of Irregular Meshes using Diffusion 
       and Curvature Flow". M. Desbrun,  M. Meyer, 
       P. Schroder, A.H.B. Caltech
    Parameters
    ------------
    mesh : trimesh.Trimesh
    Mesh to be smoothed in place
    lamb : float
    Diffusion speed constant
    If   0.0, no diffusion
    If > 0.0, diffusion occours 
    implicit_time_integration: boolean
    if False: explict time integration 
        -lamb <= 1.0 - Stability Limit (Article 1)
    if True: implict time integration 
        -lamb no limit (Article 2)
    iterations : int
    Number of passes to run filter
    laplacian_operator : None or scipy.sparse.coo.coo_matrix
    Sparse matrix laplacian operator
    Will be autogenerated if None
    """
    
    # if the laplacian operator was not passed create it here
    if laplacian_operator is None:
        laplacian_operator = laplacian_calculation(mesh)
    
    # Set volume constraint
    if volume_constraint==True:
        v_ini=mesh.volume

    # get mesh vertices as vanilla numpy array
    vertices = mesh.vertices.copy().view(np.ndarray)
    
    # Set matrix for linear system of equations
    if implicit_time_integration==True:
        dlap=laplacian_operator.shape[0]
        AA = eye(dlap) + lamb*(eye(dlap)-laplacian_operator)

    # Number of passes
    for _index in range(iterations):
        # Classic Explict Time Integration - Article 1
        if implicit_time_integration==False:
              #dot = coo_matrix.dot(laplacian_operator, vertices) - vertices
              dot = laplacian_operator.dot(vertices) - vertices
              vertices += lamb * dot

        # Implict Time Integration - Article 2
        else:
              vertices =  spsolve(AA, vertices)
        
        # Volume constraint
        if volume_constraint==True:
            vol=mass_properties(mesh.triangles,skip_inertia=True)["volume"]
            vertices *= ((v_ini/vol)**(1./3.))    

    # assign modified vertices back to mesh
    mesh.vertices = vertices
    return mesh


def filter_humphrey(mesh,
                    alpha=0.1,
                    beta=0.5,
                    iterations=10,
                    laplacian_operator=None):
    """
    Smooth a mesh in-place using laplacian smoothing
    and Humphrey filtering.

    Articles
    "Improved Laplacian Smoothing of Noisy Surface Meshes"
    J. Vollmer, R. Mencl, and H. Muller

    Parameters
    ------------
    mesh : trimesh.Trimesh
      Mesh to be smoothed in place
    alpha : float
      Controls shrinkage, range is 0.0 - 1.0
      If 0.0, not considered
      If 1.0, no smoothing
    beta : float
      Controls how aggressive smoothing is
      If 0.0, no smoothing
      If 1.0, full aggressiveness
    iterations : int
      Number of passes to run filter
    laplacian_operator : None or scipy.sparse.coo.coo_matrix
      Sparse matrix laplacian operator
      Will be autogenerated if None
    """
    # if the laplacian operator was not passed create it here
    if laplacian_operator is None:
        laplacian_operator = laplacian_calculation(mesh)

    # get mesh vertices as vanilla numpy array
    vertices = mesh.vertices.copy().view(np.ndarray)
    # save original unmodified vertices
    original = vertices.copy()

    # run through iterations of filter
    for _index in range(iterations):
        vert_q = vertices.copy()
        vertices = laplacian_operator.dot(vertices)
        vert_b = vertices - (alpha * original + (1.0 - alpha) * vert_q)
        vertices -= (beta * vert_b + (1.0 - beta) *
                     laplacian_operator.dot(vert_b))

    # assign modified vertices back to mesh
    mesh.vertices = vertices
    return mesh


def filter_taubin(mesh,
                  lamb=0.5,
                  nu=0.5,
                  iterations=10,
                  laplacian_operator=None):
    """
    Smooth a mesh in-place using laplacian smoothing
    and taubin filtering.

    Articles
    "Improved Laplacian Smoothing of Noisy Surface Meshes"
    J. Vollmer, R. Mencl, and H. Muller

    Parameters
    ------------
    mesh : trimesh.Trimesh
      Mesh to be smoothed in place.
    lamb : float
      Controls shrinkage, range is 0.0 - 1.0
    nu : float
      Controls dilation, range is 0.0 - 1.0
      Nu shall be between 0.0 < 1.0/lambda - 1.0/nu < 0.1
    iterations : int
      Number of passes to run the filter
    laplacian_operator : None or scipy.sparse.coo.coo_matrix
      Sparse matrix laplacian operator
      Will be autogenerated if None
    """
    # if the laplacian operator was not passed create it here
    if laplacian_operator is None:
        laplacian_operator = laplacian_calculation(mesh)

    # get mesh vertices as vanilla numpy array
    vertices = mesh.vertices.copy().view(np.ndarray)

    # run through multiple passes of the filter
    for index in range(iterations):
        # do a sparse dot product on the vertices
        dot = laplacian_operator.dot(vertices) - vertices
        # alternate shrinkage and dilation
        if index % 2 == 0:
            vertices += lamb * dot
        else:
            vertices -= nu * dot

    # assign updated vertices back to mesh
    mesh.vertices = vertices
    return mesh


def laplacian_calculation(mesh, equal_weight=True):
    """
    Calculate a sparse matrix for laplacian operations.

    Parameters
    -------------
    mesh : trimesh.Trimesh
      Input geometry
    equal_weight : bool
      If True, all neighbors will be considered equally
      If False, all neightbors will be weighted by inverse distance

    Returns
    ----------
    laplacian : scipy.sparse.coo.coo_matrix
      Laplacian operator
    """
    # get the vertex neighbors from the cache
    neighbors = mesh.vertex_neighbors
    # avoid hitting crc checks in loops
    vertices = mesh.vertices.view(np.ndarray)

    # stack neighbors to 1D arrays
    col = np.concatenate(neighbors)
    row = np.concatenate([[i] * len(n)
                          for i, n in enumerate(neighbors)])

    if equal_weight:
        # equal weights for each neighbor
        data = np.concatenate([[1.0 / len(n)] * len(n)
                               for n in neighbors])
    else:
        # umbrella weights, distance-weighted
        # use dot product of ones to replace array.sum(axis=1)
        ones = np.ones(3)
        # the distance from verticesex to neighbors
        norms = [1.0 / np.sqrt(np.dot((vertices[i] - vertices[n]) ** 2, ones))
                 for i, n in enumerate(neighbors)]
        # normalize group and stack into single array
        data = np.concatenate([i / i.sum() for i in norms])

    # create the sparse matrix
    matrix = coo_matrix((data, (row, col)),
                        shape=[len(vertices)] * 2)

    return matrix
