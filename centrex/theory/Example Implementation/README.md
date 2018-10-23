# Example Implementation

### Code organization

The entire implementation consists of header files that can be included as
required.

`bases/`: header files defining particular bases and the transformations between
them

`examples/`: examples of how the code can be used to solve actualy physics
problems

`operators/`: quantum operators defined on kets of particular bases, and the
infrastructure needed to generalize the operators to work on states of any other
basis

`states`: header files defining the base class `BasisState`, from which the
particular basis types get derived, and the `State<>` template class, whose
objects are superposition states in a given basis

`tests`: unit tests used in debugging

### States and bases

A quantum state is naturally represented as a C++ object, presenting a unified
interface regardless of the underlying representation, i.e. the chosen basis or
the way that basis is implemented on the computer. Nonetheless, it is useful to
leave the chosen basis in plain view; for example, when adding two quantum
states, the programmer needs to know what basis the result and the two operands
will be. The idiomatic way to express that is to let a quantum state be a
template class, templated by the basis. For example, a state object `obj`,
represented in a basis `BasisState`, is declared as follows:

    State<BasisState> obj;

Regardless of the basis, several basic operations are defined for a  `State<>`
object. For example, given two such objects `obj1` and `obj2`, we can for a
symmetric superposition

    State<> sup = (obj1 + obj2) / sqrt(2);

I have overloaded the operators `==`, `!=`, `+=`, `-=`, `*=`, `/=`, `*`, `/`,
`+`, `-` with sensible meanings. As in the above example, dividing by a number
divides the amplitudes of all components of a quantum state by that number;
addition of two states is the superposition state; a product of two states is
their inner product, and so on. See `states/State.h` for the implementation.

Much like `State<>`, the `BasisState` is also a user-defined type representing a
basis state in a given basis. Only the equality and inner product operations are
defined for such a state; for instance, a superposition of two different basis
states would not be a basis state.

However, the implementation of the basis state (as given in
`states/BasisState.h`) does not limit us to a particular choice of basis; the
class merely defines the general interface and states that the "data" of a basis
state (i.e., its quantum numbers) are to be stored in a hash map:

    protected:
       std::unordered_map<std::string, double> data;

Thus, the `BasisState` class is expected to be used as a base class. For
example, in `bases/DecoupledBasis.h`, I define the type `DecoupledBasis`,
derived from `BasisState`, with a constructor that takes all the quantum
numbers, and puts them in the `data`:

    DecoupledBasis(double J, double mJ, double I1, double m1, double I2, double m2);

### Basis transformations

### Quantum operators

An operator is a function that maps from quantum states to quantum states, most
conveniently defined through its action on the states of the basis in which it
is diagonal. For example, in the so-called `DecoupledBasis`, the `Jz` operator
takes a basis state and multiplies it by the `mJ` quantum number:

    State<DecoupledBasis> Jz(const DecoupledBasis& ket)
    {
       return ket.mJ() * ket;
    }

Having thus defined operators through their action on a set of convenient basis
states, they are automatically generalized (i.e. overloaded) in two ways:

1. They need to be able to accept superposition `ket`s of type `State<>`. Thus,
   for each operator `f(const B&)`, we need an operator that applies said `f` on
   all the kets in the superposition. [So far this is done manually, but I am
   looking for a more elegant solution.]

2. They need to be able to accept and return objects of any type derived from
   `BasisState`, and any reasonable specialization of the `State<>` template
   class. With working basis transformations, all these types should convert
   implicitly on-the-fly.
